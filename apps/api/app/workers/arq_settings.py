"""arq worker settings. Registers chunk+embed (M1.T2) and generation (M1.T3)."""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.workers.embed import chunk_and_embed
from app.workers.embed import on_startup as _embed_startup
from app.workers.generation import on_startup as _gen_startup
from app.workers.generation import run_artifact_generation
from app.workers.heartbeat import worker_heartbeat_sweeper


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def ping(ctx: dict[str, object]) -> str:
    """No-op placeholder kept so the worker boots even with no queued jobs."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    await _embed_startup(ctx)
    await _gen_startup(ctx)


class WorkerSettings:
    """arq WorkerSettings — jobs registered by task modules as they land."""

    functions: ClassVar[list[object]] = [ping, chunk_and_embed, run_artifact_generation]
    cron_jobs: ClassVar[list[object]] = [
        cron(worker_heartbeat_sweeper, second={0, 30}, run_at_startup=False)
    ]
    on_startup = startup
    redis_settings = _redis_settings()
    max_jobs = 10
    keep_result = 60 * 60  # 1 hour


def main() -> None:
    """Entrypoint for `krititva-worker` script."""
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
