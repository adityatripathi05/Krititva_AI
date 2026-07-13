"""AIOrchestrator + generation worker core + sweeper (M1.T3, FR-4.6.2-4.6.10).

Direct-service tests against real Postgres with the offline FakeLLMClient. Covers
the full enqueue authorization gate order (LLD §10), accept/reject state gating,
the worker's draft-persist core, and the stuck-job sweeper.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import FakeEmbeddingClient
from app.ai.llm_client import FakeLLMClient
from app.ai.semaphore import NullSemaphore
from app.api.errors import (
    AgentDisabled,
    AIDisabled,
    CannotProduceArtifact,
    InsufficientRole,
    InvalidJobState,
    PrereqNotApproved,
    RejectRequiresReason,
    TooManyInFlight,
)
from app.models import (
    AgentRole,
    AIGenerationJob,
    ArtifactType,
    AuditEntry,
    DocStatus,
    DocType,
    DocumentVersion,
    JobStatus,
    OrgRole,
    Project,
    ProjectMember,
    ProjectRole,
)
from app.schemas.artifacts import GenerateArtifactRequest
from app.services.ai_orchestrator import AIOrchestrator
from app.services.audit import AuditSink
from app.services.documents import DocumentService
from app.workers.generation import UnsupportedArtifact, assemble_context, generate_draft
from app.workers.heartbeat import sweep_stuck_jobs
from tests.integration._factories import make_member, make_org, make_project, make_user

pytestmark = pytest.mark.integration


class FullSemaphore:
    async def try_acquire(self, user_id: uuid.UUID) -> bool:
        return False

    async def release(self, user_id: uuid.UUID) -> None:
        return None


class Ctx:
    def __init__(
        self,
        db: AsyncSession,
        orch: AIOrchestrator,
        project: Project,
        actor_id: uuid.UUID,
        membership: ProjectMember,
    ) -> None:
        self.db = db
        self.orch = orch
        self.project = project
        self.actor_id = actor_id
        self.membership = membership


async def _ctx(db: AsyncSession, role: ProjectRole = ProjectRole.project_owner) -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    project = await make_project(db, org)
    membership = await make_member(db, project, admin, role)
    await db.flush()
    return Ctx(db, AIOrchestrator(db, AuditSink(db)), project, admin.id, membership)


def _req(agent: AgentRole, artifact: ArtifactType) -> GenerateArtifactRequest:
    return GenerateArtifactRequest(agent_role=agent, target_artifact=artifact)


async def _approve_srs(ctx: Ctx) -> None:
    docs = DocumentService(ctx.db, AuditSink(ctx.db))
    doc = await docs.create(ctx.project, DocType.srs, "SRS", ctx.actor_id)
    v = await docs.create_version(
        ctx.project, doc, ctx.actor_id, "# SRS", base_version_id=None, change_summary=None
    )
    await docs.approve(ctx.project, doc, v.id, ctx.actor_id)


# ---------------------------------------------------------------------------
# Enqueue authorization gates (LLD §10 order)
# ---------------------------------------------------------------------------


async def test_enqueue_ai_disabled(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    ctx.project.ai_enabled = False
    with pytest.raises(AIDisabled):
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.project_owner, ArtifactType.srs),
            NullSemaphore(),
        )


async def test_enqueue_agent_disabled(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    ctx.project.llm_config = {"disabled_agents": ["architect"]}
    await db_session.flush()
    with pytest.raises(AgentDisabled):
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.architect, ArtifactType.hld),
            NullSemaphore(),
        )


async def test_enqueue_cannot_produce(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    with pytest.raises(CannotProduceArtifact):
        # architect does not produce srs
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.architect, ArtifactType.srs),
            NullSemaphore(),
        )


async def test_enqueue_role_cannot_invoke(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session, role=ProjectRole.qa)
    with pytest.raises(InsufficientRole):
        # qa project role cannot invoke the architect agent
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.architect, ArtifactType.hld),
            NullSemaphore(),
        )


async def test_enqueue_prereq_missing(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    with pytest.raises(PrereqNotApproved) as exc:
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.architect, ArtifactType.hld),
            NullSemaphore(),
        )
    assert exc.value.detail["missing"] == ["srs"]


async def test_enqueue_prereq_satisfied(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    await _approve_srs(ctx)
    job = await ctx.orch.enqueue(
        ctx.project,
        ctx.actor_id,
        ctx.membership,
        _req(AgentRole.architect, ArtifactType.hld),
        NullSemaphore(),
    )
    assert job.status is JobStatus.queued


async def test_enqueue_semaphore_full(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    with pytest.raises(TooManyInFlight):
        await ctx.orch.enqueue(
            ctx.project,
            ctx.actor_id,
            ctx.membership,
            _req(AgentRole.project_owner, ArtifactType.srs),
            FullSemaphore(),
        )


async def test_enqueue_success_records_job_and_audit(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await ctx.orch.enqueue(
        ctx.project,
        ctx.actor_id,
        ctx.membership,
        _req(AgentRole.project_owner, ArtifactType.srs),
        NullSemaphore(),
    )
    assert job.status is JobStatus.queued
    assert job.retrieval_model == "nomic-embed-text"
    actions = (
        (await db_session.execute(select(AuditEntry.action).where(AuditEntry.entity == "ai_job")))
        .scalars()
        .all()
    )
    assert "ai.job_created" in actions


# ---------------------------------------------------------------------------
# Generation worker core
# ---------------------------------------------------------------------------


async def _queued_job(ctx: Ctx, artifact: ArtifactType = ArtifactType.srs) -> AIGenerationJob:
    return await ctx.orch.enqueue(
        ctx.project,
        ctx.actor_id,
        ctx.membership,
        _req(AgentRole.project_owner, artifact),
        NullSemaphore(),
    )


async def _draft(ctx: Ctx, job: AIGenerationJob) -> uuid.UUID:
    assembled = await assemble_context(ctx.db, job, FakeEmbeddingClient())
    return await generate_draft(ctx.db, job, assembled, FakeLLMClient())


async def test_generate_draft_persists_draft_version(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _queued_job(ctx)
    version_id = await _draft(ctx, job)

    version = await db_session.get(DocumentVersion, version_id)
    assert version is not None
    assert version.status is DocStatus.draft  # §1.1 — never canonical from the model
    assert version.ai_job_id == job.id
    assert job.result_document_version == version_id
    assert job.model_used == "fake/echo"
    assert job.output_tokens == 22


async def test_generate_draft_unsupported_artifact(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    # epic_breakdown produces work items, not a document — no generator yet.
    job = AIGenerationJob(
        project_id=ctx.project.id,
        requested_by=ctx.actor_id,
        agent_role=AgentRole.project_owner,
        target_artifact=ArtifactType.epic_breakdown,
        status=JobStatus.running,
    )
    db_session.add(job)
    await db_session.flush()
    with pytest.raises(UnsupportedArtifact):
        await assemble_context(db_session, job, FakeEmbeddingClient())


# ---------------------------------------------------------------------------
# Accept / reject
# ---------------------------------------------------------------------------


async def _awaiting_job(ctx: Ctx) -> AIGenerationJob:
    job = await _queued_job(ctx)
    await _draft(ctx, job)
    job.status = JobStatus.awaiting_review
    await ctx.db.flush()
    return job


async def test_accept_promotes_draft_to_canonical(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _awaiting_job(ctx)
    outcome = await ctx.orch.accept(ctx.project, job, ctx.actor_id)
    assert job.status is JobStatus.accepted
    assert outcome.document_version_id == job.result_document_version
    version = await db_session.get(DocumentVersion, outcome.document_version_id)
    assert version is not None
    assert version.status is DocStatus.approved  # §1.1 — human accept made it canonical


async def test_accept_wrong_state_rejected(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _queued_job(ctx)  # still queued, not awaiting_review
    with pytest.raises(InvalidJobState):
        await ctx.orch.accept(ctx.project, job, ctx.actor_id)


async def test_reject_marks_rejected(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _awaiting_job(ctx)
    await ctx.orch.reject(ctx.project, job, ctx.actor_id, "not good enough")
    assert job.status is JobStatus.rejected
    # The draft was NOT promoted.
    version = await db_session.get(DocumentVersion, job.result_document_version)
    assert version is not None
    assert version.status is DocStatus.draft


async def test_reject_blank_reason(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _awaiting_job(ctx)
    with pytest.raises(RejectRequiresReason):
        await ctx.orch.reject(ctx.project, job, ctx.actor_id, "   ")


# ---------------------------------------------------------------------------
# Heartbeat sweeper
# ---------------------------------------------------------------------------


async def test_sweeper_fails_stuck_running_job(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = AIGenerationJob(
        project_id=ctx.project.id,
        requested_by=ctx.actor_id,
        agent_role=AgentRole.project_owner,
        target_artifact=ArtifactType.srs,
        status=JobStatus.running,
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    db_session.add(job)
    await db_session.flush()
    swept = await sweep_stuck_jobs(db_session, redis=None)
    assert job.id in swept
    await db_session.refresh(job)
    assert job.status is JobStatus.failed


async def test_sweeper_leaves_fresh_job(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = AIGenerationJob(
        project_id=ctx.project.id,
        requested_by=ctx.actor_id,
        agent_role=AgentRole.project_owner,
        target_artifact=ArtifactType.srs,
        status=JobStatus.running,
        heartbeat_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()
    swept = await sweep_stuck_jobs(db_session, redis=None)
    assert job.id not in swept
    assert job.status is JobStatus.running
