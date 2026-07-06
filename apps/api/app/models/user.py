"""Users. Local password + optional SSO. Deactivation is soft (§FR-4.1.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, created_at, uuid_pk
from app.models.enums import OrgRole


class User(Base, TenantScopedMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    password_hash: Mapped[str | None] = mapped_column(nullable=True)  # NULL when SSO-only
    org_role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role", create_type=False, native_enum=True),
        nullable=False,
        default=OrgRole.member,
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    tz: Mapped[str] = mapped_column(nullable=False, default="UTC")
    created_at: Mapped[datetime] = created_at()
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
