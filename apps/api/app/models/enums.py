"""Python enums that mirror the Postgres ENUM types created by migration 001.

Values MUST equal names (lowercase) — Postgres native enums store the string
form. ``sa.Enum(PyEnum, name=..., create_type=False)`` maps them.
"""

from __future__ import annotations

from enum import Enum


class OrgRole(str, Enum):
    org_admin = "org_admin"
    member = "member"


class ProjectRole(str, Enum):
    project_owner = "project_owner"
    scrum_master = "scrum_master"
    developer = "developer"
    qa = "qa"
    viewer = "viewer"
    client_approver = "client_approver"


class Methodology(str, Enum):
    agile = "agile"
    waterfall = "waterfall"
    hybrid = "hybrid"


class PortalMode(str, Enum):
    none = "none"
    export_only = "export_only"
    portal = "portal"


class InvitationState(str, Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class ProjectStatus(str, Enum):
    """Free-text CHECK-constrained in the DB, but modeled here for services."""

    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"


# Names for the Postgres ENUM types. Kept in sync with migration 001.
PG_ENUM_NAMES = {
    OrgRole: "org_role",
    ProjectRole: "project_role",
    Methodology: "methodology",
    PortalMode: "portal_mode",
    InvitationState: "invitation_state",
}
