"""Append-only audit log (§FR-4.10.1, §CLAUDE.md §1.3, §1.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(nullable=False)
    entity: Mapped[str] = mapped_column(nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at()
