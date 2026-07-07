"""Refresh-token rotation ledger (NFR-5.2.2, §FR-4.1.1).

Opaque token values are never stored — only their SHA-256 hash. Rotation on
use marks the prior row ``revoked_at`` and links the new row via
``rotated_from`` so the family is auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(nullable=False, unique=True)
    issued_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_from: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(nullable=True)
    user_agent: Mapped[str | None] = mapped_column(nullable=True)
