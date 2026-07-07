"""/projects endpoints — creation, read, methodology config (FR-4.2.*, FR-4.3.*)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    require_org_role,
    require_project_membership,
)
from app.models import OrgRole, ProjectMember, ProjectRole, User
from app.schemas.methodology import (
    HierarchyRuleModel,
    HierarchyRulesReplace,
    WorkflowStateOut,
    WorkflowTransitionOut,
    WorkflowTransitionPatch,
)
from app.schemas.project import ProjectCreate, ProjectMethodologyPatch, ProjectOut
from app.services.audit import AuditSink
from app.services.project import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def _service(db: AsyncSession) -> ProjectService:
    return ProjectService(db, AuditSink(db))


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectOut]:
    """Projects visible to the caller: all org projects for an org_admin, else the
    caller's memberships."""
    projects = await _service(db).list_for_user(actor)
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    actor: User = Depends(require_org_role(OrgRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    svc = _service(db)
    project = await svc.create_project(actor, body)
    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await _service(db).get_project(project_id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}/methodology", response_model=ProjectOut)
async def change_methodology(
    project_id: uuid.UUID,
    body: ProjectMethodologyPatch,
    member: tuple[User, ProjectMember] = Depends(
        require_project_membership(ProjectRole.project_owner)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    actor, _ = member
    svc = _service(db)
    project = await svc.get_project(project_id)
    updated = await svc.change_methodology(actor, project, body.methodology, body.reseed_workflow)
    await db.commit()
    await db.refresh(updated)
    return ProjectOut.model_validate(updated)


# ---------------------------------------------------------------------------
# Methodology config (LLD §4.3)
# ---------------------------------------------------------------------------


@router.get("/{project_id}/workflow/states", response_model=list[WorkflowStateOut])
async def list_states(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowStateOut]:
    states = await _service(db).list_states(project_id)
    return [WorkflowStateOut.model_validate(s) for s in states]


@router.get("/{project_id}/workflow/transitions", response_model=list[WorkflowTransitionOut])
async def list_transitions(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowTransitionOut]:
    transitions = await _service(db).list_transitions(project_id)
    return [WorkflowTransitionOut.model_validate(t) for t in transitions]


@router.patch(
    "/{project_id}/workflow/transitions/{transition_id}",
    response_model=WorkflowTransitionOut,
)
async def update_transition(
    project_id: uuid.UUID,
    transition_id: uuid.UUID,
    body: WorkflowTransitionPatch,
    member: tuple[User, ProjectMember] = Depends(
        require_project_membership(ProjectRole.project_owner)
    ),
    db: AsyncSession = Depends(get_db),
) -> WorkflowTransitionOut:
    actor, _ = member
    svc = _service(db)
    project = await svc.get_project(project_id)
    tr = await svc.update_transition(
        actor,
        project,
        transition_id,
        is_hard_gate=body.is_hard_gate,
        required_role=body.required_role,
        approval_quorum=body.approval_quorum,
        fields_set=set(body.model_fields_set),
    )
    await db.commit()
    await db.refresh(tr)
    return WorkflowTransitionOut.model_validate(tr)


@router.get("/{project_id}/hierarchy-rules", response_model=list[HierarchyRuleModel])
async def list_hierarchy_rules(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[HierarchyRuleModel]:
    rules = await _service(db).list_hierarchy_rules(project_id)
    return [HierarchyRuleModel.model_validate(r) for r in rules]


@router.patch("/{project_id}/hierarchy-rules", response_model=list[HierarchyRuleModel])
async def replace_hierarchy_rules(
    project_id: uuid.UUID,
    body: HierarchyRulesReplace,
    member: tuple[User, ProjectMember] = Depends(
        require_project_membership(ProjectRole.project_owner)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[HierarchyRuleModel]:
    actor, _ = member
    svc = _service(db)
    project = await svc.get_project(project_id)
    rules = await svc.replace_hierarchy_rules(
        actor,
        project,
        [(r.parent_kind, r.child_kind) for r in body.rules],
    )
    await db.commit()
    return [HierarchyRuleModel.model_validate(r) for r in rules]
