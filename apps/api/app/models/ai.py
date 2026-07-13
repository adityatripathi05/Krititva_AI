"""AI generation jobs and their provenance ledger (FR-4.6.2-4.6.10, FR-4.6.4).

``ai_generation_jobs`` is project-scoped (org context flows through
``project_id``). It is mutable while a job runs — ``status`` advances
queued → running → awaiting_review → accepted/rejected/failed, and
``heartbeat_at`` ticks — but becomes immutable once ``finished_at`` is set
(§CLAUDE.md §1.3).

``ai_provenance`` is an append-only ledger written **before** the LLM call
(§CLAUDE.md §1.2): if the model hangs or crashes, the audit trail already
exists. Rows denormalize ``chunk_hash`` / ``section_path`` so a later chunk
deletion (FK ``SET NULL``) does not erase the record of what was retrieved.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk
from app.models.enums import AgentRole, ArtifactType, JobStatus


class AIGenerationJob(Base):
    __tablename__ = "ai_generation_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    agent_role: Mapped[AgentRole] = mapped_column(
        Enum(AgentRole, name="agent_role", create_type=False, native_enum=True), nullable=False
    )
    target_artifact: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="artifact_type", create_type=False, native_enum=True),
        nullable=False,
    )
    focus_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("work_items.id"), nullable=True
    )
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_type=False, native_enum=True),
        nullable=False,
        server_default="queued",
    )
    retrieval_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_document_version: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_versions.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIProvenance(Base):
    __tablename__ = "ai_provenance"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_generation_jobs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    source_chunk: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    chunk_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_item: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True
    )
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "stage IN ('lineage', 'semantic', 'operational')", name="ck_provenance_stage"
        ),
        CheckConstraint(
            "source_chunk IS NOT NULL OR source_item IS NOT NULL", name="ck_provenance_source"
        ),
    )
