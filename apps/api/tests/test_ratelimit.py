"""Per-org rate limiter core (NFR-5.2.5, §10)."""

from __future__ import annotations

import pytest

from app.api.errors import RateLimited
from app.security.ratelimit import NullRateLimiter, RedisRateLimiter


class FakeRedis:
    """Minimal async Redis stub supporting the counter ops the limiter uses."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


def _limiter(limit: int, *, now: float = 1000.0) -> tuple[RedisRateLimiter, FakeRedis]:
    redis = FakeRedis()
    return RedisRateLimiter(redis, limit, window_s=60, now=lambda: now), redis


async def test_allows_up_to_limit() -> None:
    limiter, _ = _limiter(3)
    for _ in range(3):
        await limiter.check("org-1")  # no raise


async def test_blocks_over_limit_with_retry_after() -> None:
    limiter, _ = _limiter(2)
    await limiter.check("org-1")
    await limiter.check("org-1")
    with pytest.raises(RateLimited) as exc:
        await limiter.check("org-1")
    assert exc.value.retry_after == 60
    assert exc.value.detail == {"limit": 2, "window_s": 60}


async def test_keys_are_independent() -> None:
    limiter, _ = _limiter(1)
    await limiter.check("org-1")
    await limiter.check("org-2")  # different org — its own bucket
    with pytest.raises(RateLimited):
        await limiter.check("org-1")


async def test_window_rollover_resets() -> None:
    redis = FakeRedis()
    clock = {"t": 1000.0}
    limiter = RedisRateLimiter(redis, 1, window_s=60, now=lambda: clock["t"])
    await limiter.check("org-1")
    with pytest.raises(RateLimited):
        await limiter.check("org-1")
    clock["t"] += 60  # next window
    await limiter.check("org-1")  # fresh bucket — allowed


async def test_sets_ttl_once_per_window() -> None:
    limiter, redis = _limiter(5)
    await limiter.check("org-1")
    await limiter.check("org-1")
    key = "rl:org-1:16"  # 1000 // 60
    assert redis.expires[key] == 61  # window_s + 1, set on the first hit only


async def test_zero_limit_is_noop() -> None:
    limiter, _ = _limiter(0)
    for _ in range(10):
        await limiter.check("org-1")  # limit <= 0 disables the guard


async def test_null_limiter_never_raises() -> None:
    limiter = NullRateLimiter()
    for _ in range(1000):
        await limiter.check("org-1")
