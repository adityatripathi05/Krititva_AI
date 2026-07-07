"""Auth service — login, refresh rotation, logout, invitation flow.

Routes own authorization (RBAC decorators); this service owns the credential
mechanics + persistence. All write paths audit before the outer commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EmailAlreadyRegistered
from app.config import get_settings
from app.models import (
    Invitation,
    InvitationState,
    ProjectMember,
    ProjectRole,
    RefreshToken,
    User,
)
from app.security.hashing import hash_password, verify_dummy, verify_password
from app.security.jwt import (
    encode_access_token,
    hash_opaque_token,
    new_opaque_token,
)
from app.services.audit import AuditSink


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None:
        self.db = db
        self.audit = audit

    # -----------------------------------------------------------------
    # Login / refresh / logout
    # -----------------------------------------------------------------

    async def login(
        self, email: str, password: str, user_agent: str | None = None
    ) -> tuple[User, str, str] | None:
        """Return (user, access_token, refresh_raw) or None on invalid creds."""
        stmt = select(User).where(User.email == email, User.is_active.is_(True))
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user is None:
            verify_dummy(password)  # equalize timing — no user-enumeration oracle
            return None
        if not verify_password(password, user.password_hash):
            return None
        access = encode_access_token(user.id)
        refresh_raw = await self._issue_refresh(user.id, user_agent=user_agent)
        await self.audit.write(
            action="auth.login",
            entity="user",
            entity_id=user.id,
            actor_id=user.id,
            organization_id=user.organization_id,
        )
        return user, access, refresh_raw

    async def refresh(
        self, refresh_raw: str, user_agent: str | None = None
    ) -> tuple[User, str, str] | None:
        """Rotate the refresh token. Returns None if the token is invalid/expired."""
        row = await self._find_active_refresh(refresh_raw)
        if row is None:
            return None
        row.revoked_at = _utcnow()
        row.revoked_reason = "rotated"
        user = await self.db.get(User, row.user_id)
        if user is None or not user.is_active:
            return None
        access = encode_access_token(user.id)
        new_raw = await self._issue_refresh(user.id, user_agent=user_agent, rotated_from=row.id)
        await self.audit.write(
            action="auth.refresh",
            entity="refresh_token",
            entity_id=row.id,
            actor_id=user.id,
            organization_id=user.organization_id,
        )
        return user, access, new_raw

    async def logout(self, refresh_raw: str, actor: User) -> None:
        """Idempotent: silently no-ops if the token is already invalid/expired."""
        row = await self._find_active_refresh(refresh_raw)
        if row is not None and row.user_id == actor.id:
            row.revoked_at = _utcnow()
            row.revoked_reason = "logout"
        await self.audit.write(
            action="auth.logout",
            entity="user",
            entity_id=actor.id,
            actor_id=actor.id,
            organization_id=actor.organization_id,
        )

    # -----------------------------------------------------------------
    # Invitations
    # -----------------------------------------------------------------

    async def issue_invitation(
        self,
        actor: User,
        email: str,
        project_id: uuid.UUID | None,
        project_role: ProjectRole | None,
    ) -> tuple[Invitation, str]:
        raw = new_opaque_token()
        inv = Invitation(
            organization_id=actor.organization_id,
            email=email,
            invited_by=actor.id,
            project_id=project_id,
            project_role=project_role,
            token_hash=hash_opaque_token(raw),
            expires_at=_utcnow() + timedelta(days=get_settings().invitation_ttl_days),
        )
        self.db.add(inv)
        await self.db.flush()
        await self.audit.write(
            action="invitation.issued",
            entity="invitation",
            entity_id=inv.id,
            actor_id=actor.id,
            organization_id=actor.organization_id,
            detail={
                "email": email,
                "project_id": str(project_id) if project_id else None,
            },
        )
        return inv, raw

    async def accept_invitation(
        self, raw_token: str, display_name: str, password: str
    ) -> User | None:
        """Return the newly created user, or None if the token is invalid/expired."""
        token_hash = hash_opaque_token(raw_token)
        stmt = select(Invitation).where(
            Invitation.token_hash == token_hash,
            Invitation.state == InvitationState.pending,
            Invitation.expires_at > _utcnow(),
        )
        inv = (await self.db.execute(stmt)).scalar_one_or_none()
        if inv is None:
            return None

        already = (
            await self.db.execute(select(User.id).where(User.email == inv.email))
        ).scalar_one_or_none()
        if already is not None:
            raise EmailAlreadyRegistered("an account with this email already exists")

        user = User(
            organization_id=inv.organization_id,
            email=inv.email,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        self.db.add(user)
        await self.db.flush()

        if inv.project_id and inv.project_role:
            self.db.add(
                ProjectMember(
                    project_id=inv.project_id,
                    user_id=user.id,
                    role=inv.project_role,
                )
            )

        inv.state = InvitationState.accepted
        inv.accepted_at = _utcnow()
        inv.accepted_user = user.id
        await self.db.flush()

        await self.audit.write(
            action="invitation.accepted",
            entity="user",
            entity_id=user.id,
            actor_id=user.id,
            organization_id=user.organization_id,
            detail={"invitation_id": str(inv.id)},
        )
        return user

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    async def _issue_refresh(
        self,
        user_id: uuid.UUID,
        *,
        user_agent: str | None = None,
        rotated_from: uuid.UUID | None = None,
    ) -> str:
        raw = new_opaque_token()
        row = RefreshToken(
            user_id=user_id,
            token_hash=hash_opaque_token(raw),
            expires_at=_utcnow() + timedelta(days=get_settings().jwt_refresh_ttl_days),
            rotated_from=rotated_from,
            user_agent=user_agent,
        )
        self.db.add(row)
        await self.db.flush()
        return raw

    async def _find_active_refresh(self, refresh_raw: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == hash_opaque_token(refresh_raw),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > _utcnow(),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
