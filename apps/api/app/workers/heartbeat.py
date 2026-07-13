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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.events import publish
from app.db import session_scope
from app.models import AIGenerationJob, JobStatus

SWEEP_JOB = "worker_heartbeat_sweeper"
_STALE_AFTER_S = 60


async def sweep_stuck_jobs(
    db: AsyncSession, redis: Any = None, threshold_s: int = _STALE_AFTER_S
) -> list[uuid.UUID]:
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_s)
    stmt = select(AIGenerationJob).where(
        AIGenerationJob.status == JobStatus.running,
        AIGenerationJob.heartbeat_at < cutoff,
    )
    stuck = list((await db.execute(stmt)).scalars().all())
    for job in stuck:
        job.status = JobStatus.failed
        job.error = "worker heartbeat timeout"
        job.finished_at = datetime.now(UTC)
    await db.flush()
    for job in stuck:
        await publish(redis, job.id, {"step": "failed", "error": "heartbeat timeout"})
    return [job.id for job in stuck]


async def worker_heartbeat_sweeper(ctx: dict[str, Any]) -> int:
    async with session_scope() as db:
        swept = await sweep_stuck_jobs(db, ctx.get("redis"))
        await db.commit()
    return len(swept)
