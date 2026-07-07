"""First-run bootstrap for self-hosted v1 installs (§FR-4.12.2).

The singleton ``organizations`` row is created idempotently. The first
``org_admin`` user is provisioned through ``bootstrap_setup`` from the
``POST /auth/setup`` route (M0.T7). Startup itself does NOT auto-bootstrap — the
operator must complete first-run via ``/setup``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AlreadyBootstrapped
from app.models import Organization, OrgRole, User
from app.security.hashing import hash_password
from app.services.audit import AuditSink

DEFAULT_ORG_NAME = "Krititva"


async def ensure_singleton_organization(
    db: AsyncSession, name: str = DEFAULT_ORG_NAME
) -> Organization:
    """Return the singleton org row, creating it if none exists.

    v1 self-host contract: exactly one organization row. Concurrent racers
    both succeed because we SELECT-then-INSERT inside a serializable read;
    the caller commits at the natural transaction boundary.
    """
    existing = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
    if existing is not None:
        return existing
    org = Organization(name=name)
    db.add(org)
    await db.flush()
    return org


async def has_org_admin(db: AsyncSession) -> bool:
    """True when at least one active ``org_admin`` user exists."""
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            User.org_role == OrgRole.org_admin,
            User.is_active.is_(True),
        )
    )
    return (await db.execute(stmt)).scalar_one() > 0


async def is_bootstrapped(db: AsyncSession) -> bool:
    """True when the singleton org exists AND at least one active org_admin exists."""
    org_exists = (await db.execute(select(func.count()).select_from(Organization))).scalar_one() > 0
    return org_exists and await has_org_admin(db)


async def bootstrap_setup(
    db: AsyncSession,
    audit: AuditSink,
    *,
    org_name: str,
    email: str,
    display_name: str,
    password: str,
) -> User:
    """First-run provisioning (FR-4.12.2): create the singleton org and the first
    ``org_admin``. Refuses once an org_admin already exists — the open ``/setup``
    endpoint must be a one-time door, not an admin factory."""
    if await has_org_admin(db):
        raise AlreadyBootstrapped("an org admin already exists")

    org = await ensure_singleton_organization(db, name=org_name or DEFAULT_ORG_NAME)
    admin = User(
        organization_id=org.id,
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
        org_role=OrgRole.org_admin,
    )
    db.add(admin)
    await db.flush()
    await audit.write(
        action="bootstrap.setup",
        entity="user",
        entity_id=admin.id,
        actor_id=admin.id,
        organization_id=org.id,
        detail={"org_name": org.name},
    )
    return admin
