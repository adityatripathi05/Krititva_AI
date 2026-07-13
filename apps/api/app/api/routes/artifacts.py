"""/projects/{id}/artifacts — AI generation jobs, SSE, accept/reject (FR-4.6.*).

Enqueue authorization lives in :class:`AIOrchestrator` (single source of truth
for the LLD §10 gate order); the route only resolves membership and wires the
job queue + per-user semaphore. The SSE stream replays the current job state to
late subscribers, relays worker frames from Redis pub/sub, and emits a 15 s
heartbeat (LLD §5.7).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.events import channel, is_terminal
from app.ai.semaphore import AISemaphore
from app.api.deps import (
    get_arq_pool,
    get_db,
    get_user_ai_semaphore,
    require_project_membership,
)
from app.api.errors import NotFound
from app.models import JobStatus, Project, ProjectMember, ProjectRole, User
from app.schemas.artifacts import (
    AcceptResult,
    GenerateArtifactRequest,
    GenerateArtifactResponse,
    JobStatusOut,
    ProvenanceEntry,
    RejectRequest,
)
from app.services.ai_orchestrator import AIOrchestrator
from app.services.audit import AuditSink
from app.workers.generation import GEN_JOB

router = APIRouter(prefix="/projects/{project_id}/artifacts", tags=["artifacts"])

# Accepting a job promotes an AI draft to canonical — restricted to leads, like
# document approval.
_REVIEWER_ROLES = (ProjectRole.project_owner, ProjectRole.scrum_master)

_LIVE_STATUSES = frozenset({JobStatus.queued, JobStatus.running})


def _service(db: AsyncSession) -> AIOrchestrator:
    return AIOrchestrator(db, AuditSink(db))


async def _load_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found")
    return project


@router.post("", response_model=GenerateArtifactResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_artifact(
    project_id: uuid.UUID,
    body: GenerateArtifactRequest,
    member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
    arq_pool: object | None = Depends(get_arq_pool),
    semaphore: AISemaphore = Depends(get_user_ai_semaphore),
) -> GenerateArtifactResponse:
    actor, membership = member
    project = await _load_project(db, project_id)
    job = await _service(db).enqueue(project, actor.id, membership, body, semaphore)
    await db.commit()
    if arq_pool is not None:
        await arq_pool.enqueue_job(GEN_JOB, str(job.id))  # type: ignore[attr-defined]
    return GenerateArtifactResponse(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
async def get_job(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> JobStatusOut:
    job = await _service(db).get_job(project_id, job_id)
    return JobStatusOut.model_validate(job)


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
    arq_pool: object | None = Depends(get_arq_pool),
) -> StreamingResponse:
    job = await _service(db).get_job(project_id, job_id)
    snapshot = JobStatusOut.model_validate(job).model_dump(mode="json")
    live = job.status in _LIVE_STATUSES
    return StreamingResponse(
        _event_stream(job_id, snapshot, live, arq_pool),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/{job_id}/accept", response_model=AcceptResult)
async def accept_job(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_REVIEWER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> AcceptResult:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    job = await svc.get_job(project_id, job_id)
    outcome = await svc.accept(project, job, actor.id)
    await db.commit()
    return AcceptResult(job_id=outcome.job_id, document_version_id=outcome.document_version_id)


@router.post("/jobs/{job_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_job(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    body: RejectRequest,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_REVIEWER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    job = await svc.get_job(project_id, job_id)
    await svc.reject(project, job, actor.id, body.reason)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/provenance", response_model=list[ProvenanceEntry])
async def job_provenance(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[ProvenanceEntry]:
    svc = _service(db)
    job = await svc.get_job(project_id, job_id)
    rows = await svc.list_provenance(job)
    return [ProvenanceEntry.model_validate(r) for r in rows]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(
    job_id: uuid.UUID, snapshot: dict[str, Any], live: bool, pool: Any
) -> AsyncIterator[str]:
    # Replay current state first so late subscribers are never stranded (§5.7).
    yield _sse("state", snapshot)
    if not live or pool is None:
        return
    pubsub = pool.pubsub()
    await pubsub.subscribe(channel(job_id))
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                yield _sse("heartbeat", {})
                continue
            frame = json.loads(msg["data"])
            yield _sse("progress", frame)
            if is_terminal(frame):
                break
    finally:
        await pubsub.unsubscribe(channel(job_id))
        await pubsub.aclose()
