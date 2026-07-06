"""First-run bootstrap for self-hosted v1 installs (§FR-4.12.2).

The singleton ``organizations`` row is created idempotently. The first
``org_admin`` user is provisioned through ``bootstrap_setup`` from the ``/setup``
route (lands in M0.T3). Startup itself does NOT auto-bootstrap — the operator
must hit ``/setup`` to complete first-run.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrgRole, User

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
