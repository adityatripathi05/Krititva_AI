"""Work items + links (FR-4.4.1-4.4.9).

A single polymorphic table discriminated by ``kind`` (FR-4.4.1). Work items are
project-scoped; org context flows through ``project_id``. Deferred cross-module
FKs (``source_job_id`` → ai_generation_jobs, ``to_chunk`` → document_chunks) are
plain UUID columns until M1 wires their targets.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, updated_at, uuid_pk
from app.models.enums import LinkType, WorkItemKind


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[WorkItemKind] = mapped_column(
        Enum(WorkItemKind, name="work_item_kind", create_type=False, native_enum=True),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    acceptance_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_states.id"), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sprints.id"), nullable=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id"), nullable=True
    )
    story_points: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    # COLLATE "C" — lexorank requires bytewise ordering (see migration 0007).
    rank: Mapped[str | None] = mapped_column(Text(collation="C"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    ai_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (UniqueConstraint("project_id", "seq", name="uq_work_items_project_seq"),)


class WorkItemLink(Base):
    __tablename__ = "work_item_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    from_item: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    to_item: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("work_items.id", ondelete="CASCADE"), nullable=True
    )
    to_chunk: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    link_type: Mapped[LinkType] = mapped_column(
        Enum(LinkType, name="link_type", create_type=False, native_enum=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("from_item <> to_item", name="ck_links_no_self"),
        CheckConstraint("to_item IS NOT NULL OR to_chunk IS NOT NULL", name="ck_links_target"),
    )
