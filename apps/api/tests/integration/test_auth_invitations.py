"""Invitation issue + accept (§FR-4.1.5)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgRole
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test_org_admin_can_issue_invitation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin, password="pwd")
    await db_session.commit()
    tokens = await _login(client, admin.email, "pwd")

    r = await client.post(
        "/api/v1/auth/invitations",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"email": "newhire@corp.example.com"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["invitation"]["email"] == "newhire@corp.example.com"
    assert body["token"]  # one-time, returned exactly once


async def test_member_cannot_issue_invitation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    member = await make_user(db_session, org, org_role=OrgRole.member, password="pwd")
    await db_session.commit()
    tokens = await _login(client, member.email, "pwd")

    r = await client.post(
        "/api/v1/auth/invitations",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"email": "newhire@corp.example.com"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "insufficient_role"


async def test_accept_invitation_creates_user_and_logs_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin, password="pwd")
    await db_session.commit()
    tokens = await _login(client, admin.email, "pwd")

    r1 = await client.post(
        "/api/v1/auth/invitations",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"email": "new@corp.example.com"},
    )
    assert r1.status_code == 201
    raw_token = r1.json()["token"]

    r2 = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": raw_token,
            "display_name": "New Hire",
            "password": "hunter22-safe",
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["access_token"] and body["refresh_token"]

    # Reusing the same invitation token fails.
    r3 = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": raw_token,
            "display_name": "Someone Else",
            "password": "hunter22-safe",
        },
    )
    assert r3.status_code == 410
    assert r3.json()["code"] == "invitation_invalid"


async def test_accept_invitation_bogus_token_410(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": "not-a-real-invite",
            "display_name": "X",
            "password": "hunter22-safe",
        },
    )
    assert r.status_code == 410
