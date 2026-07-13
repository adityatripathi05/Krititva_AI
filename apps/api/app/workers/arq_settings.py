"""arq worker settings. Registers the chunk+embed pipeline (M1.T2.3)."""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.config import get_settings
from app.workers.embed import chunk_and_embed
from app.workers.embed import on_startup as _embed_startup


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def ping(ctx: dict[str, object]) -> str:
    """No-op placeholder kept so the worker boots even with no queued jobs.

    arq refuses to start with zero registered functions; this keeps the worker a
    valid, idle service. Generation/SSE jobs join the list in M1.T3.
    """
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    await _embed_startup(ctx)


class WorkerSettings:
    """arq WorkerSettings — jobs registered by task modules as they land."""

    functions: ClassVar[list[object]] = [ping, chunk_and_embed]  # + generation in M1.T3
    on_startup = startup
    redis_settings = _redis_settings()
    max_jobs = 10
    keep_result = 60 * 60  # 1 hour


def main() -> None:
    """Entrypoint for `krititva-worker` script."""
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
