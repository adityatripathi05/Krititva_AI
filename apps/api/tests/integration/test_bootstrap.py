"""Bootstrap service — singleton org + org_admin detection (§FR-4.12.2)."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrgRole, User
from app.services.bootstrap import (
    ensure_singleton_organization,
    has_org_admin,
    is_bootstrapped,
)

pytestmark = pytest.mark.integration


async def test_ensure_singleton_creates_when_absent(db_session: AsyncSession) -> None:
    org = await ensure_singleton_organization(db_session, name="Krititva Test")
    await db_session.commit()
    assert org.name == "Krititva Test"
    rows = (await db_session.execute(select(Organization))).scalars().all()
    assert len(rows) == 1


async def test_ensure_singleton_is_idempotent(db_session: AsyncSession) -> None:
    a = await ensure_singleton_organization(db_session, name="First")
    await db_session.flush()
    b = await ensure_singleton_organization(db_session, name="Second")
    await db_session.commit()
    assert a.id == b.id
    assert a.name == "First"  # existing row wins


async def test_has_org_admin_toggles(db_session: AsyncSession) -> None:
    org = await ensure_singleton_organization(db_session)
    await db_session.flush()
    assert await has_org_admin(db_session) is False

    admin = User(
        organization_id=org.id,
        email=f"admin-{secrets.token_hex(4)}@krititva.test",
        display_name="Root Admin",
        org_role=OrgRole.org_admin,
    )
    db_session.add(admin)
    await db_session.commit()
    assert await has_org_admin(db_session) is True

    admin.is_active = False
    await db_session.commit()
    assert await has_org_admin(db_session) is False, "deactivated admin must not satisfy the check"


async def test_is_bootstrapped_requires_both_org_and_admin(db_session: AsyncSession) -> None:
    assert await is_bootstrapped(db_session) is False
    org = await ensure_singleton_organization(db_session)
    await db_session.flush()
    assert await is_bootstrapped(db_session) is False

    db_session.add(
        User(
            organization_id=org.id,
            email=f"root-{secrets.token_hex(4)}@krititva.test",
            display_name="Root",
            org_role=OrgRole.org_admin,
        )
    )
    await db_session.commit()
    assert await is_bootstrapped(db_session) is True
