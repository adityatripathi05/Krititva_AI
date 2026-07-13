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


class WorkItemKind(str, Enum):
    phase = "phase"
    epic = "epic"
    feature = "feature"
    story = "story"
    task = "task"
    bug = "bug"
    deliverable = "deliverable"
    test_case = "test_case"


class WorkflowCategory(str, Enum):
    """CHECK-constrained in the DB (workflow_states.category), modeled for services."""

    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class LinkType(str, Enum):
    derived_from = "derived_from"
    tests = "tests"
    blocks = "blocks"
    relates_to = "relates_to"


class DocType(str, Enum):
    srs = "srs"
    hld = "hld"
    lld = "lld"
    test_plan = "test_plan"
    other = "other"


class DocStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    superseded = "superseded"


class GateStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"


class StaleReason(str, Enum):
    chunk_removed = "chunk_removed"
    chunk_changed = "chunk_changed"
    chunk_added_upstream = "chunk_added_upstream"


class AgentRole(str, Enum):
    project_owner = "project_owner"
    architect = "architect"
    scrum_master = "scrum_master"
    developer = "developer"
    qa = "qa"


class ArtifactType(str, Enum):
    srs = "srs"
    epic_breakdown = "epic_breakdown"
    hld = "hld"
    lld = "lld"
    sprint_plan = "sprint_plan"
    story_breakdown = "story_breakdown"
    task_breakdown = "task_breakdown"
    api_contract = "api_contract"
    test_plan = "test_plan"
    test_cases = "test_cases"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    awaiting_review = "awaiting_review"
    accepted = "accepted"
    rejected = "rejected"
    failed = "failed"


class SprintState(str, Enum):
    """CHECK-constrained in the DB (sprints.state), modeled for services."""

    planned = "planned"
    active = "active"
    closed = "closed"


# Names for the Postgres ENUM types. Kept in sync with migrations 001 + 006 + 008.
PG_ENUM_NAMES = {
    OrgRole: "org_role",
    ProjectRole: "project_role",
    Methodology: "methodology",
    PortalMode: "portal_mode",
    InvitationState: "invitation_state",
    WorkItemKind: "work_item_kind",
    LinkType: "link_type",
    GateStatus: "gate_status",
    StaleReason: "stale_reason",
    DocType: "doc_type",
    DocStatus: "doc_status",
    AgentRole: "agent_role",
    ArtifactType: "artifact_type",
    JobStatus: "job_status",
}
