"""/projects/{id}/work_items endpoints — the Work Item Engine surface (FR-4.4.*)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_project_membership
from app.api.errors import NotFound
from app.models import Project, ProjectMember, ProjectRole, User
from app.schemas.work_item import (
    BulkResult,
    BulkTransitionRequest,
    LineageNode,
    LinkCreate,
    LinkOut,
    RerankRequest,
    TransitionRequest,
    WorkItemCreate,
    WorkItemOut,
    WorkItemPatch,
    work_item_out,
)
from app.services.audit import AuditSink
from app.services.work_items import WorkItemService

router = APIRouter(prefix="/projects/{project_id}/work_items", tags=["work-items"])

# Contributors who may mutate work items — viewers and client_approvers are read-only.
_CONTRIBUTOR_ROLES = (
    ProjectRole.project_owner,
    ProjectRole.scrum_master,
    ProjectRole.developer,
    ProjectRole.qa,
)


def _service(db: AsyncSession) -> WorkItemService:
    return WorkItemService(db, AuditSink(db))


async def _load_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found")
    return project


@router.post("", response_model=WorkItemOut, status_code=status.HTTP_201_CREATED)
async def create_work_item(
    project_id: uuid.UUID,
    body: WorkItemCreate,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkItemOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    item = await _service(db).create(project, actor.id, body)
    await db.commit()
    await db.refresh(item)
    return work_item_out(item, project.key)


@router.get("", response_model=list[WorkItemOut])
async def list_work_items(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[WorkItemOut]:
    project = await _load_project(db, project_id)
    items = await _service(db).list_for_project(project_id)
    return [work_item_out(i, project.key) for i in items]


@router.get("/{item_id}", response_model=WorkItemOut)
async def get_work_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> WorkItemOut:
    project = await _load_project(db, project_id)
    item = await _service(db).get(project_id, item_id)
    return work_item_out(item, project.key)


@router.patch("/{item_id}", response_model=WorkItemOut)
async def update_work_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: WorkItemPatch,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkItemOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    item = await svc.get(project_id, item_id)
    changes = body.model_dump(exclude_unset=True)
    if changes:
        await svc.update_fields(project, item, changes, actor.id)
        await db.commit()
        await db.refresh(item)
    return work_item_out(item, project.key)


@router.post("/{item_id}/transitions", response_model=WorkItemOut)
async def transition_work_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: TransitionRequest,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkItemOut:
    actor, membership = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    item = await svc.get(project_id, item_id)
    await svc.transition(project, item, membership, body.to_state_id, actor.id)
    await db.commit()
    await db.refresh(item)
    return work_item_out(item, project.key)


@router.post("/{item_id}/links", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def link_work_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: LinkCreate,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> LinkOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    item = await svc.get(project_id, item_id)
    link = await svc.link(project, item, body.to_item, body.to_chunk, body.link_type, actor.id)
    await db.commit()
    await db.refresh(link)
    return LinkOut.model_validate(link)


@router.post("/{item_id}/rerank", response_model=WorkItemOut)
async def rerank_work_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: RerankRequest,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkItemOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    item = await svc.get(project_id, item_id)
    await svc.rerank(project, item, body.before_id, body.after_id, actor.id)
    await db.commit()
    await db.refresh(item)
    return work_item_out(item, project.key)


@router.post("/bulk-transition", response_model=BulkResult)
async def bulk_transition_work_items(
    project_id: uuid.UUID,
    body: BulkTransitionRequest,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> BulkResult:
    actor, membership = member
    project = await _load_project(db, project_id)
    results = await _service(db).bulk_transition(
        project, membership, body.item_ids, body.to_state_id, actor.id
    )
    await db.commit()
    succeeded = sum(1 for r in results if r.ok)
    return BulkResult(results=results, succeeded=succeeded, failed=len(results) - succeeded)


@router.get("/{item_id}/lineage", response_model=list[LineageNode])
async def work_item_lineage(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[LineageNode]:
    svc = _service(db)
    item = await svc.get(project_id, item_id)
    return await svc.lineage(item)
