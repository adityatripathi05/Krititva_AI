"""Job-queue access for the request path (arq pool).

The API enqueues background work (e.g. chunk+embed after a document version is
created) through a shared arq pool created at app startup. Enqueueing is
best-effort: if Redis is unavailable the pool is absent and callers skip the
enqueue rather than failing the user's request — the worker's own sweep / a
later version write will still pick the work up.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings
from app.workers.embed import EMBED_JOB

_log = structlog.get_logger(__name__)


async def create_arq_pool() -> Any:
    settings = get_settings()
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_embed(pool: Any, version_id: uuid.UUID) -> None:
    """Enqueue a chunk+embed job for ``version_id``; never raise into the caller."""
    if pool is None:
        return
    try:
        await pool.enqueue_job(EMBED_JOB, str(version_id))
    except Exception as exc:  # enqueue is best-effort by design
        _log.warning("embed_enqueue_failed", version_id=str(version_id), error=str(exc))
