"""Refresh-token rotation (§NFR-5.2.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken
from app.security.jwt import hash_opaque_token
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return dict(resp.json())


async def test_refresh_rotates_token(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd12345")
    await db_session.commit()
    tokens = await _login(client, user.email, "pwd12345")

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tokens["refresh_token"], "rotation required"
    assert new["access_token"] != tokens["access_token"]


async def test_refresh_revokes_old_token(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd")
    await db_session.commit()
    tokens = await _login(client, user.email, "pwd")

    # First refresh succeeds.
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    # Reusing the OLD token fails.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    assert r2.json()["code"] == "invalid_credentials"


async def test_refresh_bogus_token_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert r.status_code == 401


async def test_expired_refresh_token_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd")
    await db_session.commit()
    tokens = await _login(client, user.email, "pwd")
    # Age it out at the DB level.
    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == hash_opaque_token(tokens["refresh_token"])
    )
    row = (await db_session.execute(stmt)).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
