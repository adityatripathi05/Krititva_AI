"""Projects (FR-4.2.2 through FR-4.2.6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, Enum, ForeignKey, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, created_at, updated_at, uuid_pk
from app.models.enums import Methodology, PortalMode, ProjectStatus


class Project(Base, TenantScopedMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("clients.id"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(unique=True, nullable=False)  # 'ACME-PORTAL'
    name: Mapped[str] = mapped_column(nullable=False)
    methodology: Mapped[Methodology] = mapped_column(
        Enum(Methodology, name="methodology", create_type=False, native_enum=True),
        nullable=False,
    )
    ai_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    llm_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    client_portal_mode: Mapped[PortalMode] = mapped_column(
        Enum(PortalMode, name="portal_mode", create_type=False, native_enum=True),
        nullable=False,
        default=PortalMode.export_only,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        nullable=False,
        default=ProjectStatus.active.value,
        server_default=ProjectStatus.active.value,
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','on_hold','completed','cancelled')",
            name="ck_projects_status",
        ),
    )
