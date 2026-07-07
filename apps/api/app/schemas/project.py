"""Pydantic request / response models for /projects (FR-4.2.1-4.2.6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Methodology, PortalMode, ProjectStatus

_KEY_PATTERN = r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$"


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=2, max_length=64, pattern=_KEY_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    methodology: Methodology
    client_id: uuid.UUID | None = None
    client_portal_mode: PortalMode = PortalMode.export_only
    ai_enabled: bool = True
    start_date: date | None = None
    target_date: date | None = None


class ProjectMethodologyPatch(BaseModel):
    """FR-4.2.3: methodology may change post-creation (warned + audited); it does
    NOT rewrite existing work items or state history."""

    model_config = ConfigDict(extra="forbid")

    methodology: Methodology
    reseed_workflow: bool = False


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    client_id: uuid.UUID | None
    key: str
    name: str
    methodology: Methodology
    ai_enabled: bool
    llm_config: dict[str, Any]
    client_portal_mode: PortalMode
    start_date: date | None
    target_date: date | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
