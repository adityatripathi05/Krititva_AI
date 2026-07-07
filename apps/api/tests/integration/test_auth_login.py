"""Login endpoint (§FR-4.1.1, NFR-5.2.1)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration


async def test_login_success_issues_tokens(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="corr3ct-horse")
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "corr3ct-horse"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


async def test_login_wrong_password_401(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="right")
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


async def test_login_unknown_email_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.example.com", "password": "x"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


async def test_login_deactivated_user_401(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session, org, password="pwd", is_active=False)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "pwd"})
    assert resp.status_code == 401
