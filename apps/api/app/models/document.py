"""Documents and their immutable version chain (FR-4.5.1-4.5.4, FR-4.5.7-4.5.9).

``documents`` is a mutable pointer row (project-scoped, so org context flows
through ``project_id``); ``document_versions`` is append-only — ``content_md``,
``content_hash`` and the chunks derived from a version never mutate (§CLAUDE.md
§1.3). Only ``status`` transitions (draft → in_review → approved → superseded)
and ``approved_at`` are set post-insert.

The ``documents ↔ document_versions`` FK cycle (LLD §2.3) is resolved in the DB
by ``fk_current_version`` added after both tables exist; the ORM models the
back-pointer as a plain ``Uuid`` column to keep mapper configuration acyclic —
the same convention used for deferred cross-module FKs elsewhere. ``ai_job_id``
is likewise a plain ``Uuid`` until ``ai_generation_jobs`` lands in M1.T3.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk
from app.models.enums import DocStatus, DocType


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[DocType] = mapped_column(
        Enum(DocType, name="doc_type", create_type=False, native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Points at the currently-approved (canonical) version; NULL until first
    # approval. FK enforced in the DB via fk_current_version (migration 0008).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = created_at()


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DocStatus] = mapped_column(
        Enum(DocStatus, name="doc_status", create_type=False, native_enum=True),
        nullable=False,
        server_default="draft",
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # FK deferred (M1.T3)
    created_at: Mapped[datetime] = created_at()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_versions_doc_no"),)
