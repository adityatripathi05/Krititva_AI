"""Shared test helpers for creating users, orgs, and projects."""

from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Methodology,
    Organization,
    OrgRole,
    Project,
    ProjectMember,
    ProjectRole,
    User,
)
from app.security.hashing import hash_password


async def make_org(db: AsyncSession, name: str = "TestOrg") -> Organization:
    org = Organization(name=name)
    db.add(org)
    await db.flush()
    return org


async def make_user(
    db: AsyncSession,
    org: Organization,
    *,
    email: str | None = None,
    password: str = "correcthorse",
    org_role: OrgRole = OrgRole.member,
    is_active: bool = True,
) -> User:
    user = User(
        organization_id=org.id,
        email=email or f"u-{secrets.token_hex(4)}@example.com",
        display_name="Test User",
        password_hash=hash_password(password),
        org_role=org_role,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def make_project(
    db: AsyncSession,
    org: Organization,
    *,
    key: str | None = None,
    methodology: Methodology = Methodology.agile,
) -> Project:
    project = Project(
        organization_id=org.id,
        key=key or f"PRJ-{secrets.token_hex(3).upper()}",
        name="Test Project",
        methodology=methodology,
    )
    db.add(project)
    await db.flush()
    return project


async def make_member(
    db: AsyncSession,
    project: Project,
    user: User,
    role: ProjectRole = ProjectRole.developer,
) -> ProjectMember:
    m = ProjectMember(project_id=project.id, user_id=user.id, role=role)
    db.add(m)
    await db.flush()
    return m
