"""Invitations for internal users and client stakeholders (§FR-4.1.5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, created_at, uuid_pk
from app.models.enums import InvitationState, ProjectRole


class Invitation(Base, TenantScopedMixin):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=True
    )
    project_role: Mapped[ProjectRole | None] = mapped_column(
        Enum(ProjectRole, name="project_role", create_type=False, native_enum=True),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(nullable=False)  # SHA-256 of the token
    state: Mapped[InvitationState] = mapped_column(
        Enum(InvitationState, name="invitation_state", create_type=False, native_enum=True),
        nullable=False,
        default=InvitationState.pending,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at()
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
