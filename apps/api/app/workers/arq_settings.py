"""arq worker settings. Real jobs land in M1.T3."""

from __future__ import annotations

from typing import ClassVar

from arq.connections import RedisSettings

from app.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """arq WorkerSettings — jobs registered by task modules as they land."""

    functions: ClassVar[list[object]] = []  # populated in M1.T3
    redis_settings = _redis_settings()
    max_jobs = 10
    keep_result = 60 * 60  # 1 hour


def main() -> None:
    """Entrypoint for `krititva-worker` script."""
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
