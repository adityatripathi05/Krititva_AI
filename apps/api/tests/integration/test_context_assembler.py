"""Context Assembler + lineage_chunks SQL (M1.T4, FR-4.6.9, FR-4.10.2).

Real Postgres (pgvector) with the offline FakeEmbeddingClient. Exercises the
lineage walk (via the SQL function, incl. cycle safety), semantic retrieval +
provenance rows, operational open-items, and budget truncation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextAssembler, RetrievalPlan
from app.ai.embeddings import DEFAULT_EMBEDDING_MODEL, FakeEmbeddingClient
from app.ai.pipeline import run_chunk_and_embed
from app.models import (
    AgentRole,
    AIGenerationJob,
    AIProvenance,
    ArtifactType,
    DocType,
    JobStatus,
    LinkType,
    OrgRole,
    Project,
    WorkItemKind,
    WorkItemLink,
)
from app.schemas.project import ProjectCreate
from app.schemas.work_item import WorkItemCreate
from app.services.audit import AuditSink
from app.services.documents import DocumentService
from app.services.project import ProjectService
from app.services.work_items import WorkItemService
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration

_MD = "# SRS\nThe system authenticates users.\n## Login\nEmail and password login flow.\n"


class Ctx:
    def __init__(
        self,
        db: AsyncSession,
        project: Project,
        actor_id: uuid.UUID,
        assembler: ContextAssembler,
    ) -> None:
        self.db = db
        self.project = project
        self.actor_id = actor_id
        self.assembler = assembler


async def _ctx(db: AsyncSession) -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.flush()
    project = await ProjectService(db, AuditSink(db)).create_project(
        admin,
        ProjectCreate(key="CTX", name="CTX", methodology="agile"),  # type: ignore[arg-type]
    )
    await db.flush()
    return Ctx(db, project, admin.id, ContextAssembler(db))


async def _approved_srs_with_chunks(ctx: Ctx) -> uuid.UUID:
    """Create an approved SRS whose chunks are embedded; return one chunk id."""
    docs = DocumentService(ctx.db, AuditSink(ctx.db))
    doc = await docs.create(ctx.project, DocType.srs, "SRS", ctx.actor_id)
    version = await docs.create_version(
        ctx.project, doc, ctx.actor_id, _MD, base_version_id=None, change_summary=None
    )
    await docs.approve(ctx.project, doc, version.id, ctx.actor_id)
    await run_chunk_and_embed(ctx.db, FakeEmbeddingClient(), version.id)
    from app.models import DocumentChunk

    chunk = (
        (
            await ctx.db.execute(
                select(DocumentChunk).where(DocumentChunk.version_id == version.id).limit(1)
            )
        )
        .scalars()
        .first()
    )
    assert chunk is not None
    return chunk.id


async def _query_vec(text: str) -> list[float]:
    return (await FakeEmbeddingClient().embed([text], DEFAULT_EMBEDDING_MODEL))[0]


# ---------------------------------------------------------------------------
# Semantic + provenance
# ---------------------------------------------------------------------------


async def test_semantic_stage_populates_and_persists_provenance(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    await _approved_srs_with_chunks(ctx)
    plan = RetrievalPlan(include_lineage=False, semantic_doc_types=[DocType.srs])
    assembled = await ctx.assembler.assemble(
        ctx.project.id, plan, None, await _query_vec("login"), DEFAULT_EMBEDDING_MODEL
    )
    assert len(assembled.semantic) >= 1
    assert all(c.stage == "semantic" and c.chunk_id is not None for c in assembled.semantic)

    job = await _job(ctx)
    await ctx.assembler.persist_provenance(job.id, assembled)
    rows = (
        (await db_session.execute(select(AIProvenance).where(AIProvenance.job_id == job.id)))
        .scalars()
        .all()
    )
    assert len(rows) == len(assembled.all_chunks())
    assert all(r.stage == "semantic" and r.source_chunk is not None for r in rows)
    assert all(r.chunk_hash is not None for r in rows)


async def _job(ctx: Ctx) -> AIGenerationJob:
    job = AIGenerationJob(
        project_id=ctx.project.id,
        requested_by=ctx.actor_id,
        agent_role=AgentRole.architect,
        target_artifact=ArtifactType.hld,
        status=JobStatus.running,
    )
    ctx.db.add(job)
    await ctx.db.flush()
    return job


# ---------------------------------------------------------------------------
# Lineage walk (lineage_chunks SQL function)
# ---------------------------------------------------------------------------


async def test_lineage_walks_derived_from_to_chunk(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    chunk_id = await _approved_srs_with_chunks(ctx)
    items = WorkItemService(db_session, AuditSink(db_session))
    epic = await items.create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.epic, title="Epic")
    )
    story = await items.create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.story, title="Story")
    )
    # epic --derived_from--> story --derived_from--> chunk
    await items.link(ctx.project, epic, story.id, None, LinkType.derived_from, ctx.actor_id)
    await items.link(ctx.project, story, None, chunk_id, LinkType.derived_from, ctx.actor_id)

    lineage = await ctx.assembler._lineage(epic.id, 6)
    assert [c.chunk_id for c in lineage] == [chunk_id]
    assert lineage[0].depth == 1
    assert lineage[0].stage == "lineage"


async def test_lineage_is_cycle_safe(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    chunk_id = await _approved_srs_with_chunks(ctx)
    items = WorkItemService(db_session, AuditSink(db_session))
    a = await items.create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.epic, title="A")
    )
    b = await items.create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.feature, title="B")
    )
    await items.link(ctx.project, a, b.id, None, LinkType.derived_from, ctx.actor_id)
    await items.link(ctx.project, b, None, chunk_id, LinkType.derived_from, ctx.actor_id)
    # A back-edge b -> a would be a cycle (the service rejects it); insert it raw
    # to prove the SQL function's visited-array guard prevents an infinite walk.
    db_session.add(WorkItemLink(from_item=b.id, to_item=a.id, link_type=LinkType.derived_from))
    await db_session.flush()

    lineage = await ctx.assembler._lineage(a.id, 6)
    assert chunk_id in {c.chunk_id for c in lineage}


# ---------------------------------------------------------------------------
# Operational + budget
# ---------------------------------------------------------------------------


async def test_operational_open_items(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    items = WorkItemService(db_session, AuditSink(db_session))
    await items.create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.story, title="Open work")
    )
    plan = RetrievalPlan(
        include_lineage=False,
        semantic_doc_types=[DocType.srs],
        include_operational=True,
        operational_scope={"open_items"},
    )
    assembled = await ctx.assembler.assemble(
        ctx.project.id, plan, None, await _query_vec("q"), DEFAULT_EMBEDDING_MODEL
    )
    assert any(
        c.stage == "operational" and c.source_item is not None for c in assembled.operational
    )


async def test_budget_truncates_total(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    await _approved_srs_with_chunks(ctx)
    plan = RetrievalPlan(include_lineage=False, semantic_doc_types=[DocType.srs], token_budget=1)
    assembled = await ctx.assembler.assemble(
        ctx.project.id, plan, None, await _query_vec("login"), DEFAULT_EMBEDDING_MODEL
    )
    assert assembled.total_tokens <= 1
