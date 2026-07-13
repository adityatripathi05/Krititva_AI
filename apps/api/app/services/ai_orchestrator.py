"""AI Orchestrator — enqueue, accept, reject (FR-4.6.2-4.6.10).

The API layer validates + authorizes + enqueues; workers do the generation
(§HLD). This service owns the enqueue authorization gates (in the order of LLD
§10), the human accept/reject actions that gate canonical state (§CLAUDE.md §1.1),
and audit composition (§1.5). Accepting a job is the explicit human action that
promotes the AI draft to canonical — it approves the draft document version.

Provenance rows are written by the Context Assembler *before* the LLM call
(§1.2); that path lands with the assembler (M1.T4). This service does not call
the LLM.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.catalog import can_produce, may_invoke_agent, prereq_doc_types
from app.ai.embeddings import DEFAULT_EMBEDDING_MODEL
from app.ai.semaphore import AISemaphore
from app.api.errors import (
    AgentDisabled,
    AIDisabled,
    CannotProduceArtifact,
    InsufficientRole,
    InvalidJobState,
    NotFound,
    PrereqNotApproved,
    RejectRequiresReason,
    TooManyInFlight,
)
from app.models import (
    AIGenerationJob,
    AIProvenance,
    DocStatus,
    Document,
    DocumentVersion,
    JobStatus,
    Project,
    ProjectMember,
)
from app.schemas.artifacts import GenerateArtifactRequest
from app.services.audit import AuditSink
from app.services.documents import DocumentService

# One source of truth for the retrieval model: chunks are embedded with this
# (M1.T2) and the query is embedded + filtered with it (M1.T4), so they must be
# identical for the semantic join to match.
_DEFAULT_RETRIEVAL_MODEL = DEFAULT_EMBEDDING_MODEL


@dataclass
class AcceptOutcome:
    job_id: uuid.UUID
    document_version_id: uuid.UUID | None


class AIOrchestrator:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None:
        self.db = db
        self.audit = audit

    # -----------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------

    async def get_job(self, project_id: uuid.UUID, job_id: uuid.UUID) -> AIGenerationJob:
        job = await self.db.get(AIGenerationJob, job_id)
        if job is None or job.project_id != project_id:
            raise NotFound("not_found")
        return job

    async def list_provenance(self, job: AIGenerationJob) -> list[AIProvenance]:
        stmt = (
            select(AIProvenance)
            .where(AIProvenance.job_id == job.id)
            .order_by(AIProvenance.stage, AIProvenance.id)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # -----------------------------------------------------------------
    # Enqueue (authorization gates in LLD §10 order)
    # -----------------------------------------------------------------

    async def enqueue(
        self,
        project: Project,
        actor_id: uuid.UUID,
        membership: ProjectMember,
        req: GenerateArtifactRequest,
        semaphore: AISemaphore,
    ) -> AIGenerationJob:
        if not project.ai_enabled:
            raise AIDisabled("AI generation is disabled for this project")
        disabled = project.llm_config.get("disabled_agents", []) if project.llm_config else []
        if req.agent_role.value in disabled:
            raise AgentDisabled(f"agent {req.agent_role.value} is disabled")
        if not can_produce(req.agent_role, req.target_artifact):
            raise CannotProduceArtifact(
                "agent role cannot produce this artifact",
                detail={
                    "agent_role": req.agent_role.value,
                    "target_artifact": req.target_artifact.value,
                },
            )
        if not may_invoke_agent(membership.role, req.agent_role):
            raise InsufficientRole(
                f"project role {membership.role.value} cannot invoke agent {req.agent_role.value}"
            )
        missing = await self._missing_prereqs(project.id, prereq_doc_types(req.target_artifact))
        if missing:
            raise PrereqNotApproved(
                "approved prerequisite document(s) missing",
                detail={"missing": sorted(missing)},
            )
        if not await semaphore.try_acquire(actor_id):
            raise TooManyInFlight("per-user AI concurrency limit reached")

        retrieval_model = _DEFAULT_RETRIEVAL_MODEL
        if project.llm_config:
            retrieval_model = project.llm_config.get("retrieval_model", _DEFAULT_RETRIEVAL_MODEL)
        job = AIGenerationJob(
            project_id=project.id,
            requested_by=actor_id,
            agent_role=req.agent_role,
            target_artifact=req.target_artifact,
            focus_item_id=req.focus_item_id,
            instructions=req.instructions,
            status=JobStatus.queued,
            retrieval_model=retrieval_model,
        )
        self.db.add(job)
        await self.db.flush()
        await self.audit.write(
            action="ai.job_created",
            entity="ai_job",
            entity_id=job.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={
                "agent_role": req.agent_role.value,
                "target_artifact": req.target_artifact.value,
            },
        )
        await self.db.flush()
        return job

    async def _missing_prereqs(self, project_id: uuid.UUID, required: frozenset[str]) -> set[str]:
        if not required:
            return set()
        stmt = (
            select(Document.doc_type)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(
                Document.project_id == project_id,
                DocumentVersion.status == DocStatus.approved,
            )
        )
        approved = {row.value for row in (await self.db.execute(stmt)).scalars().all()}
        return set(required) - approved

    # -----------------------------------------------------------------
    # Accept (human promotes the AI draft to canonical, §1.1)
    # -----------------------------------------------------------------

    async def accept(
        self, project: Project, job: AIGenerationJob, actor_id: uuid.UUID
    ) -> AcceptOutcome:
        self._require_awaiting_review(job)
        approved_version_id: uuid.UUID | None = None
        if job.result_document_version is not None:
            version = await self.db.get(DocumentVersion, job.result_document_version)
            if version is None:  # pragma: no cover - FK guarantees existence
                raise NotFound("not_found")
            document = await self.db.get(Document, version.document_id)
            if document is None:  # pragma: no cover - FK guarantees existence
                raise NotFound("not_found")
            docs = DocumentService(self.db, self.audit)
            if version.status is DocStatus.draft:
                await docs.approve(project, document, version.id, actor_id)
            approved_version_id = version.id

        job.status = JobStatus.accepted
        await self.audit.write(
            action="ai.job_accepted",
            entity="ai_job",
            entity_id=job.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"document_version": str(approved_version_id) if approved_version_id else None},
        )
        await self.db.flush()
        return AcceptOutcome(job_id=job.id, document_version_id=approved_version_id)

    # -----------------------------------------------------------------
    # Reject (human discards the AI draft; it stays non-canonical)
    # -----------------------------------------------------------------

    async def reject(
        self, project: Project, job: AIGenerationJob, actor_id: uuid.UUID, reason: str
    ) -> None:
        self._require_awaiting_review(job)
        if not reason.strip():
            raise RejectRequiresReason("a rejection reason is required")
        job.status = JobStatus.rejected
        await self.audit.write(
            action="ai.job_rejected",
            entity="ai_job",
            entity_id=job.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"reason": reason[:500]},
        )
        await self.db.flush()

    @staticmethod
    def _require_awaiting_review(job: AIGenerationJob) -> None:
        if job.status is not JobStatus.awaiting_review:
            raise InvalidJobState(
                "job is not awaiting review",
                detail={"status": job.status.value},
            )
