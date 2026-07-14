"""Artifact generation worker (FR-4.6.3-4.6.7, §CLAUDE.md §1.1/§1.2/§1.10).

``run_artifact_generation`` is the arq job. Generation is **profile-driven**: the
:class:`~app.ai.profiles.base.ProfileRegistry` resolves the ``RoleProfile`` for
``(agent_role, target_artifact)``, which supplies the retrieval policy, prompts,
output schema and draft-persistence. The pipeline runs across sessions:

    assemble context → COMMIT provenance  ─▶  LLM call  ─▶  persist DRAFT

Provenance is committed **before** the model call (§1.2). The LLM output is
parsed schema-strict with unknown fields dropped (§1.10). The result is always a
*draft* — a human must accept it before it becomes canonical (§1.1). Artifacts
with no registered profile (and not a plain document type) raise
:class:`UnsupportedArtifact`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.ai.context import AssembledContext, ContextAssembler
from app.ai.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingClient, LiteLLMEmbeddingClient
from app.ai.events import publish
from app.ai.llm_client import LLMClient as _RealLLMClient
from app.ai.llm_client import LLMClientProtocol, LLMResult, Msg
from app.ai.profiles.base import (
    PROFILE_REGISTRY,
    UnsupportedArtifact,
    resolve_generation_model,
)
from app.ai.semaphore import AISemaphore, RedisAISemaphore
from app.config import get_settings
from app.db import session_scope
from app.models import AIGenerationJob, JobStatus, Project, WorkItem
from app.services.audit import AuditSink

GEN_JOB = "run_artifact_generation"
_HEARTBEAT_INTERVAL_S = 15

_log = structlog.get_logger(__name__)

__all__ = [
    "GEN_JOB",
    "UnsupportedArtifact",
    "assemble_context",
    "generate_draft",
    "run_artifact_generation",
    "on_startup",
]


def utcnow() -> datetime:
    return datetime.now(UTC)


async def _query_text(db: Any, job: AIGenerationJob) -> str:
    """The text embedded to drive semantic retrieval (LLD §5.3 step 3)."""
    if job.focus_item_id is not None:
        item = await db.get(WorkItem, job.focus_item_id)
        if item is not None:
            return f"{item.title}\n{item.description_md}".strip()
    return job.instructions or f"Generate the {job.target_artifact.value}."


async def assemble_context(
    db: Any, job: AIGenerationJob, embedder: EmbeddingClient
) -> AssembledContext:
    """Assemble the grounding context for the job (no persistence). Raises
    :class:`UnsupportedArtifact` when no profile can produce the artifact."""
    profile = PROFILE_REGISTRY.resolve(job.agent_role, job.target_artifact)
    project = await db.get(Project, job.project_id)
    assert project is not None
    focus = await db.get(WorkItem, job.focus_item_id) if job.focus_item_id else None
    plan = await profile.retrieval_policy(db, project, focus)
    query_text = await _query_text(db, job)
    query_vec = (await embedder.embed([query_text], DEFAULT_EMBEDDING_MODEL))[0]
    return await ContextAssembler(db).assemble(
        job.project_id, plan, job.focus_item_id, query_vec, DEFAULT_EMBEDDING_MODEL
    )


async def generate_draft(
    db: Any, job: AIGenerationJob, assembled: AssembledContext, llm_client: LLMClientProtocol
) -> uuid.UUID | None:
    """Render the profile's prompts, call the model with its output schema, and
    let the profile persist the result as a DRAFT. Returns the draft document
    version id (``None`` for work-item-producing profiles). Sets the job's
    result/model/token fields; the caller owns the status transition + commit."""
    profile = PROFILE_REGISTRY.resolve(job.agent_role, job.target_artifact)
    project = await db.get(Project, job.project_id)
    assert project is not None

    messages: list[Msg] = [
        {"role": "system", "content": profile.render_system(assembled)},
        {"role": "user", "content": profile.render_user(assembled, job.instructions)},
    ]
    result: LLMResult = await llm_client.acompletion(
        model=resolve_generation_model(project, profile.model_tier),
        messages=messages,
        response_format=profile.output_schema,
        metadata={"trace_id": str(job.id)},
    )
    persisted = await profile.persist_draft(db, job, result.artifact)
    job.result_document_version = persisted.document_version_id
    job.model_used = result.model
    job.prompt_tokens = result.prompt_tokens
    job.output_tokens = result.output_tokens
    return persisted.document_version_id


async def _heartbeat_loop(job_id: uuid.UUID) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
        async with session_scope() as db:
            job = await db.get(AIGenerationJob, job_id)
            if job is None or job.status is not JobStatus.running:
                return
            job.heartbeat_at = utcnow()
            await db.commit()


async def run_artifact_generation(ctx: dict[str, Any], job_id: str) -> str:
    jid = uuid.UUID(job_id)
    llm_client: LLMClientProtocol = ctx["llm_client"]
    embedder: EmbeddingClient = ctx["embedding_client"]
    semaphore: AISemaphore = ctx["semaphore"]
    redis = ctx.get("redis")

    async with session_scope() as db:
        job = await db.get(AIGenerationJob, jid)
        if job is None:  # pragma: no cover - enqueue always precedes the job
            return "missing"
        job.status = JobStatus.running
        job.started_at = utcnow()
        job.heartbeat_at = utcnow()
        requested_by = job.requested_by
        await db.commit()

    heartbeat = asyncio.create_task(_heartbeat_loop(jid))
    try:
        # §1.2 — assemble context and COMMIT provenance before the LLM call, so
        # the audit trail survives an LLM hang/crash.
        async with session_scope() as db:
            job = await db.get(AIGenerationJob, jid)
            assert job is not None
            assembled = await assemble_context(db, job, embedder)
            await ContextAssembler(db).persist_provenance(jid, assembled)
            await db.commit()

        async with session_scope() as db:
            job = await db.get(AIGenerationJob, jid)
            assert job is not None
            version_id = await generate_draft(db, job, assembled, llm_client)
            job.status = JobStatus.awaiting_review
            job.finished_at = utcnow()
            await AuditSink(db).write(
                action="ai.draft_persisted",
                entity="ai_job",
                entity_id=job.id,
                actor_id=job.requested_by,
                project_id=job.project_id,
                detail={"draft": str(version_id)},
            )
            await db.commit()
        # The committed draft is the source of truth; the terminal frame is
        # best-effort. Swallow a pub/sub error here so it cannot fall through to
        # the outer handler and demote an already-committed awaiting_review job
        # to failed (which would also re-mutate finished_at, §1.3).
        try:
            await publish(redis, jid, {"step": "done", "draft_id": str(version_id)})
        except Exception as pub_exc:  # best-effort notification; draft is committed
            _log.warning("done_publish_failed", job_id=job_id, error=str(pub_exc))
        return "awaiting_review"
    except Exception as exc:
        _log.warning("generation_failed", job_id=job_id, error=str(exc))
        async with session_scope() as db:
            job = await db.get(AIGenerationJob, jid)
            if job is not None:
                job.status = JobStatus.failed
                job.error = str(exc)[:2000]
                job.finished_at = utcnow()
                await db.commit()
        await publish(redis, jid, {"step": "failed", "error": str(exc)[:200]})
        return "failed"
    finally:
        heartbeat.cancel()
        await semaphore.release(requested_by)


async def on_startup(ctx: dict[str, Any]) -> None:
    ctx["llm_client"] = _RealLLMClient()
    ctx.setdefault("embedding_client", LiteLLMEmbeddingClient())
    ctx["semaphore"] = RedisAISemaphore(ctx["redis"], get_settings().user_ai_concurrency)
