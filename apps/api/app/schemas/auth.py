"""Pydantic request / response models for /auth/*."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import OrgRole, ProjectRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds until access-token expiry


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    org_role: OrgRole
    is_active: bool
    tz: str
    created_at: datetime
    organization_id: uuid.UUID | None


class ProjectMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    role: ProjectRole
    allocation_pct: int


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[ProjectMembershipOut]


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


class InvitationCreate(BaseModel):
    email: EmailStr
    project_id: uuid.UUID | None = None
    project_role: ProjectRole | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    project_id: uuid.UUID | None
    project_role: ProjectRole | None
    expires_at: datetime


class InvitationIssuedResponse(BaseModel):
    invitation: InvitationOut
    token: str  # raw one-time token, returned exactly once


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=1024)
