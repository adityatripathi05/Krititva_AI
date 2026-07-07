"""Pydantic models for methodology config endpoints (FR-4.3.1-4.3.5, LLD §4.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectRole, WorkflowCategory, WorkItemKind


class WorkflowStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    key: str
    label: str
    category: WorkflowCategory
    sort_order: int


class WorkflowTransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    from_state: uuid.UUID
    to_state: uuid.UUID
    is_hard_gate: bool
    required_role: ProjectRole | None
    approval_quorum: dict[str, int]


class WorkflowTransitionPatch(BaseModel):
    """Partial update. Only provided fields are applied (route uses exclude_unset).

    ``from_state`` / ``to_state`` are structural and not editable here — removing a
    path is a delete, not an edit.
    """

    model_config = ConfigDict(extra="forbid")

    is_hard_gate: bool | None = None
    required_role: ProjectRole | None = None
    approval_quorum: dict[str, int] | None = None


class HierarchyRuleModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    parent_kind: WorkItemKind
    child_kind: WorkItemKind


class HierarchyRulesReplace(BaseModel):
    """PATCH replace-all payload (LLD §4.3)."""

    model_config = ConfigDict(extra="forbid")

    rules: list[HierarchyRuleModel] = Field(default_factory=list)
