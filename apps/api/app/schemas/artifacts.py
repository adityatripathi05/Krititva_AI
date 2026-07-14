"""Pydantic models for AI artifact generation jobs (FR-4.6.2-4.6.10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentRole, ArtifactType, JobStatus

# ---------------------------------------------------------------------------
# Architect output schema (LLD §5.5). ``srs_citations`` is required non-empty:
# every design section that consumes SRS/HLD context must cite it (§CLAUDE.md
# §7.4) — absence is a schema-validation failure. This tightens the §5.5
# "representative" default (which showed default_factory=list).
# ---------------------------------------------------------------------------


class MermaidDiagram(BaseModel):
    model_config = ConfigDict(extra="ignore")

    caption: str = Field(max_length=200)
    code: str = Field(max_length=8000)


class DesignSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    section_path: str
    body_md: str
    srs_citations: list[str] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)


class DesignDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    scope_summary: str
    sections: list[DesignSection] = Field(min_length=1)
    mermaid_diagrams: list[MermaidDiagram] = Field(default_factory=list)


# QA output schema (LLD §5.5). ``srs_citations`` required non-empty per §7.4/T6.3.
# ``story_id`` on the set is informational only — the tests are linked to the
# job's focus item, never to an LLM-emitted id (§1.10).


class TestCase(BaseModel):
    __test__ = False  # not a pytest test class despite the name

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=140)
    preconditions_md: str = ""
    steps: list[str] = Field(min_length=1)
    expected_md: str
    kind: Literal["functional", "edge", "negative", "regression"] = "functional"
    srs_citations: list[str] = Field(min_length=1)


class TestCaseSet(BaseModel):
    __test__ = False  # not a pytest test class despite the name

    model_config = ConfigDict(extra="ignore")

    cases: list[TestCase] = Field(min_length=1)
    story_id: uuid.UUID | None = None


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
    work_item_ids: list[uuid.UUID] = Field(default_factory=list)


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
