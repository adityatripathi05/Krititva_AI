"""/auth/logout and /auth/me (§FR-4.1.6)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration._factories import make_member, make_org, make_project, make_user

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test_me_returns_user_and_memberships(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd")
    project = await make_project(db_session, org)
    await make_member(db_session, project, user)
    await db_session.commit()

    tokens = await _login(client, user.email, "pwd")
    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == user.email
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["project_id"] == str(project.id)


async def test_me_without_bearer_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_with_bad_bearer_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd")
    await db_session.commit()
    tokens = await _login(client, user.email, "pwd")

    r = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 204

    # Refresh with the same token now fails.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
