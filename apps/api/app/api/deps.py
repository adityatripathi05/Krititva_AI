"""FastAPI request dependencies (auth, RBAC).

RBAC guardrail: object-level authorization goes into service classes so we
can enforce the 404-not-403 disclosure policy (§NFR-5.2.8, feedback-404-not-403).
These deps only check the caller's *identity* and *coarse* role — never
per-project membership beyond ``require_project_membership`` below.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import InsufficientRole, InvalidToken, NotFound
from app.db import get_session_factory
from app.models import OrgRole, ProjectMember, ProjectRole, User
from app.security.jwt import InvalidToken as JWTInvalidToken
from app.security.jwt import decode_access_token


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. See CLAUDE.md §4.1."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_arq_pool(request: Request) -> object | None:
    """The shared arq pool set at startup, or ``None`` when Redis is unavailable
    (or under ASGI-transport tests that skip lifespan). Enqueueing is best-effort."""
    return getattr(request.app.state, "arq_pool", None)


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Resolve the authenticated user from a Bearer access token.

    Raises ``InvalidToken`` on missing/malformed/expired tokens or when the
    user has been deactivated. RBAC checks happen in ``require_*`` deps below.
    """
    token = _extract_bearer(request)
    if token is None:
        raise InvalidToken("missing bearer token")
    try:
        user_id = decode_access_token(token)
    except JWTInvalidToken as exc:
        raise InvalidToken(str(exc)) from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidToken("user not active")
    return user


def require_org_role(*allowed: OrgRole) -> Callable[..., Awaitable[User]]:
    """Dependency factory: caller must hold one of ``allowed`` org roles."""
    allowed_set = frozenset(allowed)

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.org_role not in allowed_set:
            raise InsufficientRole(f"required one of: {[r.value for r in allowed_set]}")
        return user

    return _check


def require_project_membership(
    *allowed_roles: ProjectRole,
) -> Callable[..., Awaitable[tuple[User, ProjectMember]]]:
    """Dependency factory: caller must be a member of the URL's ``project_id``.

    Returns ``(user, membership)``. Missing project OR missing membership
    → ``NotFound`` (404), never 403 (§NFR-5.2.8). Wrong role → ``InsufficientRole``
    (403) because the caller has legitimate visibility into the project.
    """
    allowed_role_set: frozenset[ProjectRole] | None = (
        frozenset(allowed_roles) if allowed_roles else None
    )

    async def _check(
        project_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[User, ProjectMember]:
        stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
        membership = (await db.execute(stmt)).scalar_one_or_none()
        if membership is None:
            # Suppress membership disclosure — 404 whether the project doesn't
            # exist or the caller simply isn't a member.
            raise NotFound("not_found")
        if allowed_role_set is not None and membership.role not in allowed_role_set:
            raise InsufficientRole(f"required project role: {[r.value for r in allowed_role_set]}")
        return user, membership

    return _check


def require_agent_permission(
    agent_role: str,
) -> Callable[..., Awaitable[tuple[User, ProjectMember]]]:
    """Dependency factory: caller may invoke the named AI agent role.

    v1 mapping (mirrors LLD §3.1 `may_invoke_agent`): ``project_owner`` can invoke
    any agent; ``scrum_master`` can invoke SM + Dev + QA; developers → Dev + QA;
    QA → QA; viewer/client_approver → none. Lands here as a coarse gate; the
    concrete matrix comes with M1.T3.
    """
    matrix: dict[ProjectRole, frozenset[str]] = {
        ProjectRole.project_owner: frozenset(
            {"project_owner", "architect", "scrum_master", "developer", "qa"}
        ),
        ProjectRole.scrum_master: frozenset({"scrum_master", "developer", "qa"}),
        ProjectRole.developer: frozenset({"developer", "qa"}),
        ProjectRole.qa: frozenset({"qa"}),
    }

    async def _check(
        project_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[User, ProjectMember]:
        stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
        membership = (await db.execute(stmt)).scalar_one_or_none()
        if membership is None:
            raise NotFound("not_found")
        if agent_role not in matrix.get(membership.role, frozenset()):
            raise InsufficientRole(f"role cannot invoke {agent_role}")
        return user, membership

    return _check


__all__ = [
    "get_db",
    "get_arq_pool",
    "get_current_user",
    "require_org_role",
    "require_project_membership",
    "require_agent_permission",
]
