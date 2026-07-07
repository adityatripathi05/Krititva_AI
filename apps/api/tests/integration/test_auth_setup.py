"""First-run bootstrap endpoint (FR-4.12.2, M0.T7.1).

Each integration test starts against an empty (migrated) schema, so the DB is
genuinely un-bootstrapped at the top of every test.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_SETUP = {
    "org_name": "Acme Agency",
    "email": "founder@example.com",
    "display_name": "Founder",
    "password": "correcthorse",
}


async def test_bootstrap_status_false_then_true(client: AsyncClient) -> None:
    before = await client.get("/api/v1/auth/bootstrap")
    assert before.status_code == 200
    assert before.json() == {"bootstrapped": False}

    created = await client.post("/api/v1/auth/setup", json=_SETUP)
    assert created.status_code == 201, created.text
    assert created.json()["token_type"] == "bearer"

    after = await client.get("/api/v1/auth/bootstrap")
    assert after.json() == {"bootstrapped": True}


async def test_setup_creates_org_admin_who_can_call_me(client: AsyncClient) -> None:
    tokens = (await client.post("/api/v1/auth/setup", json=_SETUP)).json()
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["org_role"] == "org_admin"
    assert body["user"]["email"] == "founder@example.com"
    assert body["user"]["organization_id"] is not None


async def test_setup_is_one_time(client: AsyncClient) -> None:
    first = await client.post("/api/v1/auth/setup", json=_SETUP)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/setup",
        json={**_SETUP, "email": "intruder@example.com"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "already_bootstrapped"


async def test_setup_rejects_short_password(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/setup", json={**_SETUP, "password": "short"})
    assert r.status_code == 422
