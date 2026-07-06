"""Insert + query roundtrip for every identity/tenancy model."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Client,
    Invitation,
    InvitationState,
    Methodology,
    Organization,
    OrgRole,
    PortalMode,
    Project,
    ProjectMember,
    ProjectRole,
    User,
)

pytestmark = pytest.mark.integration


async def test_organization_and_user_roundtrip(db_session: AsyncSession) -> None:
    org = Organization(name="ACME Studios")
    db_session.add(org)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"admin-{secrets.token_hex(4)}@acme.test",
        display_name="Ada Admin",
        org_role=OrgRole.org_admin,
    )
    db_session.add(user)
    await db_session.commit()

    fetched = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert fetched.org_role is OrgRole.org_admin
    assert fetched.organization_id == org.id
    assert fetched.is_active is True
    assert fetched.tz == "UTC"


async def test_client_and_project_roundtrip(db_session: AsyncSession) -> None:
    org = Organization(name="Agency Org")
    db_session.add(org)
    await db_session.flush()

    client = Client(organization_id=org.id, name="Big Bank")
    db_session.add(client)
    await db_session.flush()

    project = Project(
        organization_id=org.id,
        client_id=client.id,
        key=f"BANK-{secrets.token_hex(3).upper()}",
        name="Bank Portal",
        methodology=Methodology.waterfall,
        client_portal_mode=PortalMode.portal,
    )
    db_session.add(project)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(Project).where(Project.id == project.id))
    ).scalar_one()
    assert fetched.methodology is Methodology.waterfall
    assert fetched.client_portal_mode is PortalMode.portal
    assert fetched.status == "active"
    assert fetched.ai_enabled is True
    assert fetched.llm_config == {}


async def test_project_member_composite_pk(db_session: AsyncSession) -> None:
    org = Organization(name="Squad")
    db_session.add(org)
    await db_session.flush()
    user = User(
        organization_id=org.id,
        email=f"dev-{secrets.token_hex(4)}@squad.test",
        display_name="Dee Dev",
    )
    project = Project(
        organization_id=org.id,
        key=f"SQD-{secrets.token_hex(3).upper()}",
        name="Squad Project",
        methodology=Methodology.agile,
    )
    db_session.add_all([user, project])
    await db_session.flush()

    membership = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role=ProjectRole.developer,
        allocation_pct=80,
    )
    db_session.add(membership)
    await db_session.commit()

    fetched = (
        await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one()
    assert fetched.role is ProjectRole.developer
    assert fetched.allocation_pct == 80


async def test_invitation_lifecycle_fields(db_session: AsyncSession) -> None:
    org = Organization(name="Inv Org")
    db_session.add(org)
    await db_session.flush()
    inviter = User(
        organization_id=org.id,
        email=f"pm-{secrets.token_hex(4)}@inv.test",
        display_name="Priya PM",
        org_role=OrgRole.org_admin,
    )
    db_session.add(inviter)
    await db_session.flush()

    inv = Invitation(
        organization_id=org.id,
        email="new-hire@inv.test",
        invited_by=inviter.id,
        token_hash="a" * 64,
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
    )
    db_session.add(inv)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(Invitation).where(Invitation.id == inv.id))
    ).scalar_one()
    assert fetched.state is InvitationState.pending
    assert fetched.accepted_user is None
    assert fetched.accepted_at is None
