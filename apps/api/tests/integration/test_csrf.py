"""CSRF middleware (§NFR-5.2.9)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.security.csrf import CSRFMiddleware
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def csrf_client() -> AsyncIterator[AsyncClient]:
    """App with only the CSRF middleware + one non-exempt state-changing route.

    Isolates the CSRF check from the auth-endpoint exemptions used by ``client``.
    """
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/warmup")
    async def _warmup() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/protected")
    async def _protected() -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_csrf_cookie_is_set_on_first_response(client: AsyncClient) -> None:
    s = get_settings()
    r = await client.get("/livez")
    assert r.status_code == 200
    assert s.csrf_cookie_name in r.cookies


async def test_bearer_requests_are_exempt(client: AsyncClient, db_session: AsyncSession) -> None:
    """Bearer-authenticated requests skip CSRF check even when a cookie exists."""
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd")
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "pwd"})
    assert r.status_code == 200  # CSRF cookie now set on the client
    access = r.json()["access_token"]

    # Even without an X-CSRF-Token header, Bearer auth is exempt.
    r2 = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": r.json()["refresh_token"]},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 204


async def test_session_cookie_request_without_csrf_header_403(
    csrf_client: AsyncClient,
) -> None:
    """A cookie-bearing request to a non-exempt endpoint without ``X-CSRF-Token`` is rejected."""
    s = get_settings()
    await csrf_client.get("/warmup")
    assert s.csrf_cookie_name in csrf_client.cookies

    r = await csrf_client.post("/protected")
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_mismatch"


async def test_session_cookie_request_with_matching_header_passes(
    csrf_client: AsyncClient,
) -> None:
    s = get_settings()
    await csrf_client.get("/warmup")
    token = csrf_client.cookies.get(s.csrf_cookie_name)
    assert token

    r = await csrf_client.post("/protected", headers={s.csrf_header_name: token})
    assert r.status_code == 200
