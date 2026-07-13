"""arq worker settings. Real jobs land in M1.T3."""

from __future__ import annotations

from typing import ClassVar

from arq.connections import RedisSettings

from app.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def ping(ctx: dict[str, object]) -> str:
    """No-op placeholder so the worker boots before real jobs land (M1.T3).

    arq refuses to start with zero registered functions; this keeps the worker a
    valid, idle service in M0. Real tasks (embed_chunks, generation, …) join the
    ``functions`` list in M1.T3.
    """
    return "pong"


class WorkerSettings:
    """arq WorkerSettings — jobs registered by task modules as they land."""

    functions: ClassVar[list[object]] = [ping]  # + real jobs in M1.T3
    redis_settings = _redis_settings()
    max_jobs = 10
    keep_result = 60 * 60  # 1 hour


def main() -> None:
    """Entrypoint for `krititva-worker` script."""
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
