"""Per-org rate limiting wired into the app (NFR-5.2.5, §10).

Overrides ``get_rate_limiter`` with a shared low-limit limiter so the second
authenticated request to a resource router is rejected with 429 + Retry-After.
The default test client leaves rate limiting off (no arq pool → NullRateLimiter),
so this is the only place the wired 429 is exercised.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_rate_limiter
from app.main import create_app
from app.models import OrgRole, User
from app.security.jwt import encode_access_token
from app.security.ratelimit import RedisRateLimiter
from tests.integration._factories import make_org, make_user
from tests.test_ratelimit import FakeRedis

pytestmark = pytest.mark.integration


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user.id)}"}


async def test_second_request_rate_limited(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    # One shared limiter instance across requests so the counter accumulates.
    limiter = RedisRateLimiter(FakeRedis(), limit=1, window_s=30, now=lambda: 1000.0)

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = await ac.get("/api/v1/projects", headers=_bearer(admin))
        assert first.status_code == 200, first.text
        second = await ac.get("/api/v1/projects", headers=_bearer(admin))
        assert second.status_code == 429
        assert second.json()["code"] == "rate_limited"
        assert second.headers["retry-after"] == "30"
    app.dependency_overrides.clear()


async def test_health_is_not_rate_limited(db_session: AsyncSession) -> None:
    limiter = RedisRateLimiter(FakeRedis(), limit=1, window_s=30, now=lambda: 1000.0)
    app = create_app()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(3):
            r = await ac.get("/livez")
            assert r.status_code == 200
    app.dependency_overrides.clear()
