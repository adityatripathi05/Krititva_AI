"""Pydantic models for AI artifact generation jobs (FR-4.6.2-4.6.10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentRole, ArtifactType, JobStatus


class GenerateArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_role: AgentRole
    target_artifact: ArtifactType
    focus_item_id: uuid.UUID | None = None
    instructions: str | None = Field(default=None, max_length=4000)


class GenerateArtifactResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus = JobStatus.queued


class JobStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    agent_role: AgentRole
    target_artifact: ArtifactType
    status: JobStatus
    focus_item_id: uuid.UUID | None
    result_document_version: uuid.UUID | None
    model_used: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AcceptResult(BaseModel):
    job_id: uuid.UUID
    document_version_id: uuid.UUID | None


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class ProvenanceEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage: str
    source_chunk: uuid.UUID | None
    chunk_hash: str | None
    section_path: str | None
    source_item: uuid.UUID | None
    similarity: float | None
