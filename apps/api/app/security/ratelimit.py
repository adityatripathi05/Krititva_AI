"""Per-organization request rate limiting (NFR-5.2.5, §10).

A Redis fixed-window counter: at most ``limit`` requests per ``window_s`` seconds
for a given key (the caller's organization). State lives in Redis so the limit
holds across API processes, mirroring the per-user AI semaphore. When Redis is
unavailable (dev/test) a :class:`NullRateLimiter` disables the limit, exactly as
the semaphore falls back to :class:`NullSemaphore`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from app.api.errors import RateLimited


class RateLimiter(Protocol):
    async def check(self, key: str) -> None:
        """Record a hit for ``key``; raise :class:`RateLimited` if over budget."""
        ...


class RedisRateLimiter:
    """Fixed-window counter. The window key rolls every ``window_s`` seconds; a
    boundary-straddling burst can admit up to ~2x ``limit`` briefly, which is an
    accepted trade for a cheap single-INCR guard."""

    def __init__(
        self,
        redis: Any,
        limit: int,
        window_s: int,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._limit = limit
        self._window_s = max(1, window_s)
        self._now = now

    async def check(self, key: str) -> None:
        if self._limit <= 0:
            return
        bucket = int(self._now() // self._window_s)
        rkey = f"rl:{key}:{bucket}"
        count = await self._redis.incr(rkey)
        if count == 1:
            # +1 so the window key outlives the bucket it counts, avoiding a race
            # where the key expires mid-window and resets the count.
            await self._redis.expire(rkey, self._window_s + 1)
        if count > self._limit:
            raise RateLimited(
                "per-organization request rate limit exceeded",
                detail={"limit": self._limit, "window_s": self._window_s},
                retry_after=self._window_s,
            )


class NullRateLimiter:
    """No-op limiter used when rate limiting is disabled or Redis is absent."""

    async def check(self, key: str) -> None:
        return None
