"""/auth/* endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_org_role
from app.api.errors import InsufficientRole, InvalidCredentials, InvitationInvalid
from app.config import get_settings
from app.models import OrgRole, ProjectMember, User
from app.schemas.auth import (
    InvitationAcceptRequest,
    InvitationCreate,
    InvitationIssuedResponse,
    InvitationOut,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    ProjectMembershipOut,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.services.audit import AuditSink
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:200] if ua else None


def _token_pair(access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=get_settings().jwt_access_ttl_minutes * 60,
    )


# ---------------------------------------------------------------------------
# Login / refresh / logout
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    svc = AuthService(db, AuditSink(db))
    result = await svc.login(body.email, body.password, _user_agent(request))
    if result is None:
        raise InvalidCredentials("invalid email or password")
    await db.commit()
    _user, access, refresh = result
    return _token_pair(access, refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    svc = AuthService(db, AuditSink(db))
    result = await svc.refresh(body.refresh_token, _user_agent(request))
    if result is None:
        raise InvalidCredentials("invalid refresh token")
    await db.commit()
    _user, access, new_refresh = result
    return _token_pair(access, new_refresh)


@router.post("/logout", response_class=Response)
async def logout(
    body: LogoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    svc = AuthService(db, AuditSink(db))
    await svc.logout(body.refresh_token, user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    stmt = select(ProjectMember).where(ProjectMember.user_id == user.id)
    memberships = (await db.execute(stmt)).scalars().all()
    return MeResponse(
        user=UserOut.model_validate(user),
        memberships=[ProjectMembershipOut.model_validate(m) for m in memberships],
    )


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@router.post(
    "/invitations",
    response_model=InvitationIssuedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_invitation(
    body: InvitationCreate,
    actor: User = Depends(require_org_role(OrgRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> InvitationIssuedResponse:
    """Issue an invitation. v1 gates to org_admin — project-scoped invites by
    project_owners land in M0.T4 once ProjectService is in."""
    # Enforce (project_id, project_role) come as a pair
    if bool(body.project_id) ^ bool(body.project_role):
        raise InsufficientRole("project_id and project_role must be provided together")

    svc = AuthService(db, AuditSink(db))
    inv, raw = await svc.issue_invitation(actor, body.email, body.project_id, body.project_role)
    await db.commit()
    return InvitationIssuedResponse(invitation=InvitationOut.model_validate(inv), token=raw)


@router.post("/invitations/accept", response_model=TokenPair)
async def accept_invitation(
    body: InvitationAcceptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Public: accept an invitation and log the new user in immediately."""
    svc = AuthService(db, AuditSink(db))
    user = await svc.accept_invitation(body.token, body.display_name, body.password)
    if user is None:
        raise InvitationInvalid("invitation not found or expired")
    # Issue tokens directly — the just-created user is authenticated by the
    # invitation acceptance itself, no need to re-verify credentials.
    login_result = await svc.login(user.email, body.password, _user_agent(request))
    assert login_result is not None
    await db.commit()
    _u, access, refresh_raw = login_result
    return _token_pair(access, refresh_raw)
