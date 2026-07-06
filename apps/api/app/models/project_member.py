"""Project membership + per-project role (§FR-4.1.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Enum, ForeignKey, SmallInteger, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at
from app.models.enums import ProjectRole


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role", create_type=False, native_enum=True),
        nullable=False,
    )
    allocation_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
    added_at: Mapped[datetime] = created_at()

    __table_args__ = (
        CheckConstraint(
            "allocation_pct BETWEEN 0 AND 100",
            name="ck_project_members_allocation",
        ),
    )
