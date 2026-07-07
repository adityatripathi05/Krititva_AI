"""Pydantic models for work items, links, ranking, bulk ops (FR-4.4.*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import LinkType, WorkItemKind
from app.models.work_item import WorkItem


class WorkItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: WorkItemKind
    title: str = Field(min_length=1, max_length=500)
    parent_id: uuid.UUID | None = None
    description_md: str = ""
    acceptance_md: str | None = None
    assignee_id: uuid.UUID | None = None
    sprint_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    story_points: Decimal | None = Field(default=None, ge=0)
    estimated_hours: Decimal | None = Field(default=None, ge=0)


class WorkItemPatch(BaseModel):
    """Field-level edit. State moves go through the transition endpoint, and
    ``kind`` / ``parent_id`` are structural (re-parent is a separate concern)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description_md: str | None = None
    acceptance_md: str | None = None
    assignee_id: uuid.UUID | None = None
    sprint_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    story_points: Decimal | None = Field(default=None, ge=0)
    estimated_hours: Decimal | None = Field(default=None, ge=0)
    actual_hours: Decimal | None = Field(default=None, ge=0)


class WorkItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    kind: WorkItemKind
    parent_id: uuid.UUID | None
    seq: int
    key: str
    title: str
    description_md: str
    acceptance_md: str | None
    state_id: uuid.UUID
    assignee_id: uuid.UUID | None
    sprint_id: uuid.UUID | None
    milestone_id: uuid.UUID | None
    story_points: Decimal | None
    estimated_hours: Decimal | None
    actual_hours: Decimal | None
    rank: str | None
    ai_generated: bool
    stale: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


def work_item_out(item: WorkItem, project_key: str) -> WorkItemOut:
    """Serialize a work item, composing the human key ``<project.key>-<seq>`` (FR-4.4.2)."""
    return WorkItemOut(
        id=item.id,
        project_id=item.project_id,
        kind=item.kind,
        parent_id=item.parent_id,
        seq=item.seq,
        key=f"{project_key}-{item.seq}",
        title=item.title,
        description_md=item.description_md,
        acceptance_md=item.acceptance_md,
        state_id=item.state_id,
        assignee_id=item.assignee_id,
        sprint_id=item.sprint_id,
        milestone_id=item.milestone_id,
        story_points=item.story_points,
        estimated_hours=item.estimated_hours,
        actual_hours=item.actual_hours,
        rank=item.rank,
        ai_generated=item.ai_generated,
        stale=item.stale,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_state_id: uuid.UUID


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_item: uuid.UUID | None = None
    to_chunk: uuid.UUID | None = None
    link_type: LinkType

    @model_validator(mode="after")
    def _exactly_one_target(self) -> LinkCreate:
        if (self.to_item is None) == (self.to_chunk is None):
            raise ValueError("exactly one of to_item / to_chunk must be set")
        return self


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_item: uuid.UUID
    to_item: uuid.UUID | None
    to_chunk: uuid.UUID | None
    link_type: LinkType


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_id: uuid.UUID | None = None
    after_id: uuid.UUID | None = None


class BulkTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    to_state_id: uuid.UUID


class BulkItemResult(BaseModel):
    id: uuid.UUID
    ok: bool
    error_code: str | None = None


class BulkResult(BaseModel):
    results: list[BulkItemResult]
    succeeded: int
    failed: int


class LineageNode(BaseModel):
    id: uuid.UUID
    kind: WorkItemKind
    seq: int
    title: str
    depth: int
