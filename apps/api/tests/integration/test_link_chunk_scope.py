"""Cross-project chunk-link scoping (review finding #1; FR-4.1.3, NFR-5.2.8).

``WorkItemService.link`` must reject a ``to_chunk`` that belongs to another
project — otherwise lineage retrieval would pull a foreign project's document
content into this project's AI context.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import FakeEmbeddingClient
from app.ai.pipeline import run_chunk_and_embed
from app.api.errors import NotFound
from app.models import DocType, DocumentChunk, LinkType, OrgRole, Project, WorkItemKind
from app.schemas.project import ProjectCreate
from app.schemas.work_item import WorkItemCreate
from app.services.audit import AuditSink
from app.services.documents import DocumentService
from app.services.project import ProjectService
from app.services.work_items import WorkItemService
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration

_MD = "# SRS\nThe system authenticates users.\n## Login\nEmail and password flow.\n"


async def _project(db: AsyncSession, admin: object, key: str) -> Project:
    return await ProjectService(db, AuditSink(db)).create_project(
        admin,  # type: ignore[arg-type]
        ProjectCreate(key=key, name=key, methodology="agile"),  # type: ignore[arg-type]
    )


async def _chunk_id(db: AsyncSession, project: Project, actor_id: uuid.UUID) -> uuid.UUID:
    docs = DocumentService(db, AuditSink(db))
    doc = await docs.create(project, DocType.srs, "SRS", actor_id)
    version = await docs.create_version(
        project, doc, actor_id, _MD, base_version_id=None, change_summary=None
    )
    await docs.approve(project, doc, version.id, actor_id)
    await run_chunk_and_embed(db, FakeEmbeddingClient(), version.id)
    chunk = (
        (await db.execute(select(DocumentChunk).where(DocumentChunk.version_id == version.id)))
        .scalars()
        .first()
    )
    assert chunk is not None
    return chunk.id


async def test_link_foreign_chunk_is_404(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.flush()
    proj_a = await _project(db_session, admin, "AAA")
    proj_b = await _project(db_session, admin, "BBB")
    await db_session.flush()

    foreign_chunk = await _chunk_id(db_session, proj_b, admin.id)
    wi = WorkItemService(db_session, AuditSink(db_session))
    item_a = await wi.create(
        proj_a, admin.id, WorkItemCreate(kind=WorkItemKind.story, title="A story")
    )

    with pytest.raises(NotFound):
        await wi.link(proj_a, item_a, None, foreign_chunk, LinkType.derived_from, admin.id)


async def test_link_own_chunk_succeeds(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.flush()
    proj_a = await _project(db_session, admin, "AAA")
    await db_session.flush()

    own_chunk = await _chunk_id(db_session, proj_a, admin.id)
    wi = WorkItemService(db_session, AuditSink(db_session))
    item_a = await wi.create(
        proj_a, admin.id, WorkItemCreate(kind=WorkItemKind.story, title="A story")
    )
    link = await wi.link(proj_a, item_a, None, own_chunk, LinkType.derived_from, admin.id)
    assert link.to_chunk == own_chunk


async def test_link_nonexistent_chunk_is_404(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.flush()
    proj_a = await _project(db_session, admin, "AAA")
    await db_session.flush()

    wi = WorkItemService(db_session, AuditSink(db_session))
    item_a = await wi.create(
        proj_a, admin.id, WorkItemCreate(kind=WorkItemKind.story, title="A story")
    )
    with pytest.raises(NotFound):
        await wi.link(proj_a, item_a, None, uuid.uuid4(), LinkType.derived_from, admin.id)
