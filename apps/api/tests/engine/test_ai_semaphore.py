"""Per-user AI concurrency semaphore (M1.T3.3, NFR-5.2.5).

Pure unit test against an in-memory fake Redis — the acquire/release arithmetic
is what enforces the cap, so it is tested directly without a live Redis.
"""

from __future__ import annotations

import uuid

from app.ai.semaphore import RedisAISemaphore


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    async def set(self, key: str, value: int) -> None:
        self.store[key] = value


async def test_semaphore_caps_and_releases() -> None:
    redis = FakeRedis()
    sem = RedisAISemaphore(redis, limit=3)
    user = uuid.uuid4()

    assert await sem.try_acquire(user) is True
    assert await sem.try_acquire(user) is True
    assert await sem.try_acquire(user) is True
    # 4th over the cap of 3.
    assert await sem.try_acquire(user) is False
    # The rejected attempt did not leave the counter inflated.
    assert redis.store["ai:inflight:" + str(user)] == 3

    await sem.release(user)
    assert await sem.try_acquire(user) is True


async def test_semaphore_is_per_user() -> None:
    redis = FakeRedis()
    sem = RedisAISemaphore(redis, limit=1)
    a, b = uuid.uuid4(), uuid.uuid4()
    assert await sem.try_acquire(a) is True
    assert await sem.try_acquire(a) is False
    # A different user has their own slot.
    assert await sem.try_acquire(b) is True


async def test_release_never_goes_negative() -> None:
    redis = FakeRedis()
    sem = RedisAISemaphore(redis, limit=2)
    user = uuid.uuid4()
    await sem.release(user)  # release without acquire
    assert redis.store["ai:inflight:" + str(user)] == 0
