"""Declarative base and shared column helpers.

Every tenant-scoped table subclasses ``TenantScopedMixin`` so ``organization_id``
lives in exactly one place (§FR-4.1.3). The column is nullable at the DB level
in v1 self-host but populated on every INSERT — see ``.claude/CLAUDE.md`` §1.9.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root of the ORM hierarchy. All model classes inherit from this."""


def uuid_pk() -> Mapped[uuid.UUID]:
    """Standard PK: server-generated via ``gen_random_uuid()``."""
    return mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


def updated_at() -> Mapped[datetime]:
    """Only on mutable tables. Append-only tables (§CLAUDE.md §1.3) omit this."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class TenantScopedMixin:
    """Mixin adding the nullable ``organization_id`` column (§FR-4.1.3).

    Populated by services on every INSERT even though the column is nullable
    at the DB level — this keeps the future multi-tenant migration a backfill.
    """

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
