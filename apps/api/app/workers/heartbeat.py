"""Stuck-job sweeper (FR-4.6.8, NFR-5.3.1).

A running job whose ``heartbeat_at`` is older than the threshold is assumed dead
(crashed worker) and moved to ``failed``, with a terminal frame published so any
SSE subscriber is released. Runs as an arq cron; the pure core
:func:`sweep_stuck_jobs` is unit-testable against a session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.events import publish
from app.ai.semaphore import AISemaphore
from app.db import session_scope
from app.models import AIGenerationJob, JobStatus

SWEEP_JOB = "worker_heartbeat_sweeper"
_STALE_AFTER_S = 60
# A queued job that never started is orphaned (enqueue failed, or the process
# died between committing the row and enqueueing the task). Use a generous grace
# so a job merely waiting in a backlog is not reaped.
_QUEUED_STALE_AFTER_S = 300


async def sweep_stuck_jobs(
    db: AsyncSession,
    redis: Any = None,
    threshold_s: int = _STALE_AFTER_S,
    semaphore: AISemaphore | None = None,
    queued_threshold_s: int = _QUEUED_STALE_AFTER_S,
) -> list[uuid.UUID]:
    now = datetime.now(UTC)
    running_cutoff = now - timedelta(seconds=threshold_s)
    queued_cutoff = now - timedelta(seconds=queued_threshold_s)
    stmt = select(AIGenerationJob).where(
        or_(
            (AIGenerationJob.status == JobStatus.running)
            & (AIGenerationJob.heartbeat_at < running_cutoff),
            (AIGenerationJob.status == JobStatus.queued)
            & (AIGenerationJob.started_at.is_(None))
            & (AIGenerationJob.created_at < queued_cutoff),
        )
    )
    stuck = list((await db.execute(stmt)).scalars().all())
    for job in stuck:
        job.error = (
            "worker heartbeat timeout"
            if job.status == JobStatus.running
            else "orphaned in queue (never started)"
        )
        job.status = JobStatus.failed
        job.finished_at = now
    await db.flush()
    for job in stuck:
        # Reclaim the concurrency slot the crashed/orphaned job still holds
        # (its worker finally never ran), ahead of the TTL backstop.
        if semaphore is not None:
            await semaphore.release(job.requested_by)
        await publish(redis, job.id, {"step": "failed", "error": job.error})
    return [job.id for job in stuck]


async def worker_heartbeat_sweeper(ctx: dict[str, Any]) -> int:
    async with session_scope() as db:
        swept = await sweep_stuck_jobs(db, ctx.get("redis"), semaphore=ctx.get("semaphore"))
        await db.commit()
    return len(swept)
