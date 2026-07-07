"""Sprints, milestones, and stale flags (§LLD 2.2).

Project-scoped scheduling primitives. Milestone multi-sig approvals land in M2
(`milestone_approvals`); this milestone ships the base table. ``stale_flags`` is
created empty — the stale-detection sweep populates it once documents exist (M1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, updated_at, uuid_pk
from app.models.enums import GateStatus, StaleReason, WorkItemKind


class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="planned")

    __table_args__ = (
        CheckConstraint("state IN ('planned', 'active', 'closed')", name="ck_sprints_state"),
        CheckConstraint("ends_on > starts_on", name="ck_sprints_dates"),
    )


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phase_kind: Mapped[WorkItemKind | None] = mapped_column(
        Enum(WorkItemKind, name="work_item_kind", create_type=False, native_enum=True),
        nullable=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_hard_gate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    gate_status: Mapped[GateStatus] = mapped_column(
        Enum(GateStatus, name="gate_status", create_type=False, native_enum=True),
        nullable=False,
        server_default="pending",
    )
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class StaleFlag(Base):
    __tablename__ = "stale_flags"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reason: Mapped[StaleReason] = mapped_column(
        Enum(StaleReason, name="stale_reason", create_type=False, native_enum=True),
        nullable=False,
    )
    detail_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        CheckConstraint("target_kind IN ('document', 'work_item')", name="ck_stale_target_kind"),
    )
