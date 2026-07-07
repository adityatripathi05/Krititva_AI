"""Methodology configuration tables (FR-4.3.1-4.3.5).

These are *data*, not code: Agile/Waterfall/Hybrid differences live entirely in
``workflow_states`` / ``workflow_transitions`` / ``hierarchy_rules`` rows seeded
from ``packages/methodology-templates/`` on project creation (§CLAUDE.md §1.8).
They are project-scoped and therefore carry no ``organization_id`` — org context
flows through ``project_id`` → ``projects``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk
from app.models.enums import ProjectRole, WorkItemKind


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint(
            "category IN ('todo', 'in_progress', 'done')",
            name="ck_workflow_states_category",
        ),
        UniqueConstraint("project_id", "key", name="uq_workflow_states_project_key"),
    )


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False
    )
    to_state: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False
    )
    is_hard_gate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    required_role: Mapped[ProjectRole | None] = mapped_column(
        Enum(ProjectRole, name="project_role", create_type=False, native_enum=True),
        nullable=True,
    )
    approval_quorum: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "from_state",
            "to_state",
            name="uq_workflow_transitions_project_from_to",
        ),
    )


class HierarchyRule(Base):
    __tablename__ = "hierarchy_rules"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    parent_kind: Mapped[WorkItemKind] = mapped_column(
        Enum(WorkItemKind, name="work_item_kind", create_type=False, native_enum=True),
        primary_key=True,
    )
    child_kind: Mapped[WorkItemKind] = mapped_column(
        Enum(WorkItemKind, name="work_item_kind", create_type=False, native_enum=True),
        primary_key=True,
    )
