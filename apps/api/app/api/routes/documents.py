"""/projects/{id}/documents endpoints — document authoring + versioning (FR-4.5.*).

PDF export (``GET .../export.pdf``, M1.T1.4) is intentionally not wired here yet;
it needs a headless renderer whose dependency licensing is still under review.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_arq_pool, get_db, require_project_membership
from app.api.errors import NotFound
from app.models import Project, ProjectMember, ProjectRole, User
from app.queue import enqueue_embed
from app.schemas.document import (
    DocumentCreate,
    DocumentOut,
    DocumentVersionCreate,
    DocumentVersionOut,
    document_out,
    document_version_out,
)
from app.services.audit import AuditSink
from app.services.documents import DocumentService

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])

# Contributors may author documents and draft versions.
_CONTRIBUTOR_ROLES = (
    ProjectRole.project_owner,
    ProjectRole.scrum_master,
    ProjectRole.developer,
    ProjectRole.qa,
)
# Approving a version mutates canonical project state — restricted to leads.
_APPROVER_ROLES = (ProjectRole.project_owner, ProjectRole.scrum_master)


def _service(db: AsyncSession) -> DocumentService:
    return DocumentService(db, AuditSink(db))


async def _load_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found")
    return project


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    project_id: uuid.UUID,
    body: DocumentCreate,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    doc = await _service(db).create(project, body.doc_type, body.title, actor.id)
    await db.commit()
    await db.refresh(doc)
    return document_out(doc)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    project_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    docs = await _service(db).list_documents(project_id)
    return [document_out(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await _service(db).get_document(project_id, document_id)
    return document_out(doc)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionOut])
async def list_versions(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentVersionOut]:
    svc = _service(db)
    doc = await svc.get_document(project_id, document_id)
    versions = await svc.list_versions(doc)
    return [document_version_out(v) for v in versions]


@router.post(
    "/{document_id}/versions",
    response_model=DocumentVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentVersionCreate,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_CONTRIBUTOR_ROLES)),
    db: AsyncSession = Depends(get_db),
    arq_pool: object | None = Depends(get_arq_pool),
) -> DocumentVersionOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    doc = await svc.get_document(project_id, document_id)
    version = await svc.create_version(
        project,
        doc,
        actor.id,
        body.content_md,
        body.base_version_id,
        body.change_summary,
    )
    await db.commit()
    await db.refresh(version)
    await enqueue_embed(arq_pool, version.id)
    return document_version_out(version)


@router.get("/{document_id}/versions/{version_id}", response_model=DocumentVersionOut)
async def get_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    _member: tuple[User, ProjectMember] = Depends(require_project_membership()),
    db: AsyncSession = Depends(get_db),
) -> DocumentVersionOut:
    svc = _service(db)
    doc = await svc.get_document(project_id, document_id)
    version = await svc.get_version(doc, version_id)
    return document_version_out(version)


@router.post("/{document_id}/versions/{version_id}/approve", response_model=DocumentVersionOut)
async def approve_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    member: tuple[User, ProjectMember] = Depends(require_project_membership(*_APPROVER_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> DocumentVersionOut:
    actor, _ = member
    project = await _load_project(db, project_id)
    svc = _service(db)
    doc = await svc.get_document(project_id, document_id)
    version = await svc.approve(project, doc, version_id, actor.id)
    await db.commit()
    await db.refresh(version)
    return document_version_out(version)
