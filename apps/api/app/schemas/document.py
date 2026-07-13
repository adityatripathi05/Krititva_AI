"""Pydantic models for documents and their immutable versions (FR-4.5.*)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import Document, DocumentVersion
from app.models.enums import DocStatus, DocType


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    title: str = Field(min_length=1, max_length=500)


class DocumentVersionCreate(BaseModel):
    """A new draft version. ``base_version_id`` is the version the author edited
    from — it must match the document's current head or the write is rejected
    with ``version_conflict`` (optimistic locking, FR-4.5.7). ``None`` means the
    author expects to create the very first version."""

    model_config = ConfigDict(extra="forbid")

    content_md: str
    base_version_id: uuid.UUID | None = None
    change_summary: str | None = Field(default=None, max_length=1000)


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_no: int
    content_md: str
    content_hash: str
    status: DocStatus
    change_summary: str | None
    created_by: uuid.UUID
    ai_job_id: uuid.UUID | None
    created_at: datetime
    approved_at: datetime | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    doc_type: DocType
    title: str
    current_version_id: uuid.UUID | None
    created_at: datetime


def document_out(doc: Document) -> DocumentOut:
    return DocumentOut.model_validate(doc)


def document_version_out(version: DocumentVersion) -> DocumentVersionOut:
    return DocumentVersionOut.model_validate(version)
