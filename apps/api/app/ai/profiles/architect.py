"""Architect agent — produces HLD and LLD design documents (M1.T5, FR-4.6.1).

Retrieves the approved SRS (and HLD, for the LLD) semantically, prompts a
frontier model for a section-structured :class:`DesignDocument` with mandatory
per-section citations (§CLAUDE.md §7.4), and persists it as a **draft** document
version. Mermaid diagrams are preserved as fenced ```mermaid blocks.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.catalog import ARTIFACT_DOC_TYPE
from app.ai.context import AssembledContext, RetrievalPlan
from app.ai.profiles.base import PersistResult
from app.ai.templating import render_template
from app.models import AIGenerationJob, Project, WorkItem
from app.models.enums import AgentRole, ArtifactType, DocType
from app.schemas.artifacts import DesignDocument, DesignSection
from app.services.audit import AuditSink
from app.services.documents import DocumentService

_TOKEN_BUDGET = 24000


class MissingCitations(RuntimeError):
    """A generated design section carried no citation (§7.4)."""


class ArchitectProfile:
    role = AgentRole.architect
    artifacts = frozenset({ArtifactType.hld, ArtifactType.lld})
    model_tier = "frontier"
    output_schema: type[BaseModel] = DesignDocument

    async def retrieval_policy(
        self, db: AsyncSession, project: Project, focus_item: WorkItem | None
    ) -> RetrievalPlan:
        return RetrievalPlan(
            include_lineage=focus_item is not None,
            semantic_doc_types=[DocType.srs, DocType.hld],
            semantic_k=24,
            token_budget=_TOKEN_BUDGET,
        )

    def render_system(self, assembled: AssembledContext) -> str:
        return render_template("architect_system.j2", doc_type="design")

    def render_user(self, assembled: AssembledContext, instructions: str | None) -> str:
        return render_template(
            "architect_user.j2",
            doc_type="design document",
            instructions=instructions,
            context=assembled.render(),
        )

    async def persist_draft(
        self, db: AsyncSession, job: AIGenerationJob, artifact: BaseModel
    ) -> PersistResult:
        assert isinstance(artifact, DesignDocument)
        _validate_citations(artifact)
        doc_type = ARTIFACT_DOC_TYPE.get(job.target_artifact, DocType.hld)
        project = await db.get(Project, job.project_id)
        assert project is not None
        body_md = _render_body(artifact)
        docs = DocumentService(db, AuditSink(db))
        document = await docs.create(project, doc_type, artifact.title, job.requested_by)
        version = await docs.create_version(
            project,
            document,
            job.requested_by,
            body_md,
            base_version_id=None,
            change_summary="AI-generated design draft",
            ai_job_id=job.id,
        )
        return PersistResult(document_version_id=version.id)


def _validate_citations(doc: DesignDocument) -> None:
    """Per-section citation validation (T5.4). The schema already requires a
    non-empty list; this guards against whitespace-only entries."""
    for section in doc.sections:
        if not any(c.strip() for c in section.srs_citations):
            raise MissingCitations(f"section '{section.heading}' has no citation")


def _render_body(doc: DesignDocument) -> str:
    parts: list[str] = [f"# {doc.title}", "", doc.scope_summary, ""]
    for section in doc.sections:
        parts.append(_render_section(section))
    for diagram in doc.mermaid_diagrams:
        parts.append(f"\n_{diagram.caption}_\n\n```mermaid\n{diagram.code}\n```")
    return "\n".join(parts).strip() + "\n"


def _render_section(section: DesignSection) -> str:
    lines = [f"## {section.section_path} {section.heading}", "", section.body_md, ""]
    lines.append("_Citations: " + ", ".join(section.srs_citations) + "_")
    if section.open_questions:
        lines.append("\n**Open questions:**")
        lines.extend(f"- {q}" for q in section.open_questions)
    return "\n".join(lines) + "\n"
