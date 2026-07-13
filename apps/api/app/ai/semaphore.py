"""Per-user AI-job concurrency limit (NFR-5.2.5).

A user may have at most ``limit`` generation jobs in flight (default 3, from
``settings.user_ai_concurrency``). The API acquires a slot before enqueueing; the
worker releases it when the job reaches a terminal state. State lives in Redis so
the limit holds across API/worker processes.

Acquire is atomic (INCR-then-check-then-DECR-on-overflow) and each key carries a
TTL as a leak-guard so a crashed worker cannot permanently consume a slot.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

# Leak-guard: a slot auto-frees after this many seconds even if release() never
# runs (crashed worker). Comfortably longer than the LLM timeout budget.
_SLOT_TTL_S = 3600


def _key(user_id: uuid.UUID) -> str:
    return f"ai:inflight:{user_id}"


class AISemaphore(Protocol):
    async def try_acquire(self, user_id: uuid.UUID) -> bool: ...
    async def release(self, user_id: uuid.UUID) -> None: ...


class RedisAISemaphore:
    def __init__(self, redis: Any, limit: int) -> None:
        self._redis = redis
        self._limit = limit

    async def try_acquire(self, user_id: uuid.UUID) -> bool:
        key = _key(user_id)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, _SLOT_TTL_S)
        if count > self._limit:
            await self._redis.decr(key)
            return False
        return True

    async def release(self, user_id: uuid.UUID) -> None:
        key = _key(user_id)
        remaining = await self._redis.decr(key)
        if remaining < 0:
            await self._redis.set(key, 0)


class NullSemaphore:
    """Always-acquires fallback used when Redis is unavailable (dev/test without a
    running queue). Production always has Redis, so the real limit applies there."""

    async def try_acquire(self, user_id: uuid.UUID) -> bool:
        return True

    async def release(self, user_id: uuid.UUID) -> None:
        return None
