"""Context Assembler (FR-4.6.9, FR-4.10.2 · LLD §5.2-5.3).

Assembles the grounding context for a generation in three stages —
**lineage-first** (chunks reachable from the focus item via ``derived_from``),
then **semantic** (vector-nearest approved chunks), then **operational** (open
work items) — packs them into a token budget, and records every retained source
as an ``ai_provenance`` row. The worker persists that provenance and commits it
**before** the LLM call (§CLAUDE.md §1.2).

Token counting reuses the offline estimator from the chunker (tiktoken is avoided
— its vocab download would breach the no-phone-home default, §1.6).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.catalog import prereq_doc_types
from app.ai.chunking import estimate_tokens
from app.ai.retrieval import semantic_search_scored
from app.models import AIProvenance, WorkflowState, WorkItem
from app.models.enums import ArtifactType, DocType, WorkflowCategory

# A summarizer compresses several chunk bodies into one short text (overflow
# fallback, T4.5). Injected so tests can use a deterministic fake.
Summarizer = Callable[[list[str]], Awaitable[str]]

_OPERATIONAL_OPEN_ITEMS = "open_items"
_MAX_OPERATIONAL = 20


@dataclass
class RetrievalPlan:
    include_lineage: bool = True
    lineage_max_depth: int = 6
    semantic_doc_types: list[DocType] = field(default_factory=list)
    semantic_k: int = 20
    include_operational: bool = False
    operational_scope: set[str] = field(default_factory=set)
    token_budget: int = 12000


@dataclass(frozen=True)
class ContextChunk:
    stage: str  # 'lineage' | 'semantic' | 'operational'
    content: str
    token_count: int
    chunk_id: uuid.UUID | None = None
    section_path: str | None = None
    content_hash: str | None = None
    similarity: float | None = None
    source_item: uuid.UUID | None = None
    depth: int | None = None
    summarized_from: tuple[uuid.UUID, ...] = ()


@dataclass
class AssembledContext:
    lineage: list[ContextChunk]
    semantic: list[ContextChunk]
    operational: list[ContextChunk]
    total_tokens: int

    def all_chunks(self) -> list[ContextChunk]:
        return [*self.lineage, *self.semantic, *self.operational]

    def render(self) -> str:
        """Wrap each chunk in a delimited block and keep it clearly as data —
        the system prompt instructs the model to ignore embedded instructions
        (§CLAUDE.md §7.5)."""
        blocks: list[str] = []
        for c in self.all_chunks():
            label = c.section_path or c.stage
            blocks.append(f'<<<CONTEXT stage={c.stage} ref="{label}">>>\n{c.content}\n<<<END>>>')
        return "\n\n".join(blocks)


def pack_to_budget(
    lineage: Sequence[ContextChunk],
    semantic: Sequence[ContextChunk],
    operational: Sequence[ContextChunk],
    budget: int,
) -> AssembledContext:
    """Greedily pack by priority (lineage > semantic > operational), preserving
    within-stage order, never exceeding ``budget`` tokens."""
    remaining = budget
    packed: dict[str, list[ContextChunk]] = {"lineage": [], "semantic": [], "operational": []}
    for name, group in (("lineage", lineage), ("semantic", semantic), ("operational", operational)):
        for chunk in group:
            if chunk.token_count <= remaining:
                packed[name].append(chunk)
                remaining -= chunk.token_count
    return AssembledContext(
        lineage=packed["lineage"],
        semantic=packed["semantic"],
        operational=packed["operational"],
        total_tokens=budget - remaining,
    )


def default_plan_for(artifact: ArtifactType, focus_item_id: uuid.UUID | None) -> RetrievalPlan:
    """Stand-in for ``profile.retrieval_policy`` until role profiles land
    (M1.T5/T6): retrieve semantically from the artifact's approved prerequisites
    (or the core doc types), and include lineage only when a focus item is given."""
    prereqs = [DocType(x) for x in sorted(prereq_doc_types(artifact))]
    doc_types = prereqs or [DocType.srs, DocType.hld, DocType.lld, DocType.test_plan]
    return RetrievalPlan(
        include_lineage=focus_item_id is not None,
        semantic_doc_types=doc_types,
    )


async def summarize_lineage_fallback(
    lineage: list[ContextChunk], budget: int, summarizer: Summarizer
) -> list[ContextChunk]:
    """When lineage alone overflows the budget, keep the shallowest nodes (up to
    half the budget) and fold the oldest/deepest ones into a single summary node
    (T4.5). The summary retains its source chunk ids for provenance."""
    ordered = sorted(lineage, key=lambda c: (c.depth if c.depth is not None else 0))
    kept: list[ContextChunk] = []
    to_fold: list[ContextChunk] = []
    used = 0
    half = max(1, budget // 2)
    for chunk in ordered:
        if used + chunk.token_count <= half:
            kept.append(chunk)
            used += chunk.token_count
        else:
            to_fold.append(chunk)
    if not to_fold:
        return kept
    summary_text = await summarizer([c.content for c in to_fold])
    summary = ContextChunk(
        stage="lineage",
        content=summary_text,
        token_count=estimate_tokens(summary_text),
        summarized_from=tuple(c.chunk_id for c in to_fold if c.chunk_id is not None),
    )
    return [*kept, summary]


class ContextAssembler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def assemble(
        self,
        project_id: uuid.UUID,
        plan: RetrievalPlan,
        focus_item_id: uuid.UUID | None,
        query_vec: Sequence[float],
        embedding_model: str,
        summarizer: Summarizer | None = None,
    ) -> AssembledContext:
        lineage: list[ContextChunk] = []
        if plan.include_lineage and focus_item_id is not None:
            lineage = await self._lineage(focus_item_id, plan.lineage_max_depth)

        if sum(c.token_count for c in lineage) > plan.token_budget and summarizer is not None:
            lineage = await summarize_lineage_fallback(lineage, plan.token_budget, summarizer)

        used_ids = [c.chunk_id for c in lineage if c.chunk_id is not None]
        semantic = await self._semantic(project_id, plan, query_vec, embedding_model, used_ids)
        operational = await self._operational(project_id, plan)
        return pack_to_budget(lineage, semantic, operational, plan.token_budget)

    async def _lineage(self, focus_item_id: uuid.UUID, max_depth: int) -> list[ContextChunk]:
        rows = (
            await self.db.execute(
                text(
                    "SELECT chunk_id, section_path, content, depth "
                    "FROM lineage_chunks(:focus, :depth)"
                ),
                {"focus": focus_item_id, "depth": max_depth},
            )
        ).all()
        return [
            ContextChunk(
                stage="lineage",
                chunk_id=r.chunk_id,
                section_path=r.section_path,
                content=r.content,
                content_hash=_hash(r.content),
                token_count=estimate_tokens(r.content),
                depth=r.depth,
            )
            for r in rows
        ]

    async def _semantic(
        self,
        project_id: uuid.UUID,
        plan: RetrievalPlan,
        query_vec: Sequence[float],
        embedding_model: str,
        exclude_ids: Sequence[uuid.UUID],
    ) -> list[ContextChunk]:
        scored = await semantic_search_scored(
            self.db,
            project_id=project_id,
            doc_types=plan.semantic_doc_types,
            embedding_model=embedding_model,
            query_vec=query_vec,
            k=plan.semantic_k,
            exclude_ids=exclude_ids,
        )
        return [
            ContextChunk(
                stage="semantic",
                chunk_id=chunk.id,
                section_path=chunk.section_path,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                similarity=similarity,
            )
            for chunk, similarity in scored
        ]

    async def _operational(self, project_id: uuid.UUID, plan: RetrievalPlan) -> list[ContextChunk]:
        # v1 supports 'open_items'; 'sprint' / 'capacity' land with those
        # services (M2/M3).
        if not plan.include_operational or _OPERATIONAL_OPEN_ITEMS not in plan.operational_scope:
            return []
        stmt = (
            select(WorkItem)
            .join(WorkflowState, WorkflowState.id == WorkItem.state_id)
            .where(
                WorkItem.project_id == project_id,
                WorkflowState.category != WorkflowCategory.done.value,
            )
            .order_by(WorkItem.seq)
            .limit(_MAX_OPERATIONAL)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        out: list[ContextChunk] = []
        for item in items:
            body = f"{item.title}\n{item.description_md}".strip()
            out.append(
                ContextChunk(
                    stage="operational",
                    source_item=item.id,
                    content=body,
                    token_count=estimate_tokens(body),
                )
            )
        return out

    async def persist_provenance(self, job_id: uuid.UUID, assembled: AssembledContext) -> None:
        """Write one ``ai_provenance`` row per retained source. Called by the
        worker and committed BEFORE the LLM call (§1.2)."""
        for chunk in assembled.all_chunks():
            if chunk.summarized_from:
                for source in chunk.summarized_from:
                    self.db.add(AIProvenance(job_id=job_id, stage=chunk.stage, source_chunk=source))
                continue
            self.db.add(
                AIProvenance(
                    job_id=job_id,
                    stage=chunk.stage,
                    source_chunk=chunk.chunk_id,
                    chunk_hash=chunk.content_hash,
                    section_path=chunk.section_path,
                    source_item=chunk.source_item,
                    similarity=chunk.similarity,
                )
            )
        await self.db.flush()


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
