"""Direct DocumentService tests — versioning, optimistic lock, approval
(FR-4.5.1-4.5.4, FR-4.5.7-4.5.9, FR-4.10.4).

Calls the service against a real Postgres session (no HTTP layer): coverage.py
does not trace coroutines run through the httpx ASGI transport, so these tests
are what prove — and measure — the optimistic-lock and approval branches.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import InvalidDocumentState, NotFound, VersionConflict
from app.models import (
    AuditEntry,
    DocStatus,
    DocType,
    Document,
    OrgRole,
)
from app.services.audit import AuditSink
from app.services.documents import DocumentService, _content_hash
from tests.integration._factories import make_org, make_project, make_user

pytestmark = pytest.mark.integration


class Ctx:
    def __init__(self, svc: DocumentService, project: object, actor_id: uuid.UUID) -> None:
        self.svc = svc
        self.project = project
        self.actor_id = actor_id


async def _ctx(db: AsyncSession) -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    project = await make_project(db, org)
    await db.flush()
    return Ctx(DocumentService(db, AuditSink(db)), project, admin.id)


async def _doc(ctx: Ctx) -> Document:
    return await ctx.svc.create(ctx.project, DocType.srs, "System SRS", ctx.actor_id)


# ---------------------------------------------------------------------------
# create + create_version basics
# ---------------------------------------------------------------------------


async def test_create_document_has_no_current_version(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    assert doc.current_version_id is None
    assert doc.doc_type is DocType.srs


async def test_first_version_no_base_gets_version_one(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "# Draft", base_version_id=None, change_summary="init"
    )
    assert v1.version_no == 1
    assert v1.status is DocStatus.draft
    assert v1.content_hash == _content_hash("# Draft")
    # Draft creation must NOT touch the canonical pointer.
    assert doc.current_version_id is None


async def test_version_no_increments_on_matching_base(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    v2 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "two", base_version_id=v1.id, change_summary=None
    )
    assert v2.version_no == 2
    # Immutability: the earlier version's content is untouched by the new one.
    assert v1.content_md == "one"
    assert v2.content_md == "two"


# ---------------------------------------------------------------------------
# optimistic lock — every branch
# ---------------------------------------------------------------------------


async def test_none_base_conflicts_when_head_exists(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    with pytest.raises(VersionConflict) as exc:
        await ctx.svc.create_version(
            ctx.project, doc, ctx.actor_id, "two", base_version_id=None, change_summary=None
        )
    assert exc.value.detail["head_version_id"] == str(v1.id)
    assert exc.value.detail["head_version_no"] == 1


async def test_stale_base_conflicts(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "two", base_version_id=v1.id, change_summary=None
    )
    # v1 is no longer head; basing a new write on it is stale.
    with pytest.raises(VersionConflict):
        await ctx.svc.create_version(
            ctx.project, doc, ctx.actor_id, "three", base_version_id=v1.id, change_summary=None
        )


async def test_base_supplied_but_no_versions_conflicts(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    with pytest.raises(VersionConflict) as exc:
        await ctx.svc.create_version(
            ctx.project,
            doc,
            ctx.actor_id,
            "x",
            base_version_id=uuid.uuid4(),
            change_summary=None,
        )
    assert exc.value.detail == {}


# ---------------------------------------------------------------------------
# approve — single-approved invariant + supersession
# ---------------------------------------------------------------------------


async def test_approve_sets_canonical_pointer(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    approved = await ctx.svc.approve(ctx.project, doc, v1.id, ctx.actor_id)
    assert approved.status is DocStatus.approved
    assert approved.approved_at is not None
    assert doc.current_version_id == v1.id


async def test_approve_supersedes_prior(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    await ctx.svc.approve(ctx.project, doc, v1.id, ctx.actor_id)
    v2 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "two", base_version_id=v1.id, change_summary=None
    )
    await ctx.svc.approve(ctx.project, doc, v2.id, ctx.actor_id)

    await db_session.refresh(v1)
    assert v1.status is DocStatus.superseded
    assert doc.current_version_id == v2.id
    # The single-approved partial unique index is satisfied: exactly one approved.
    approved = (
        (await db_session.execute(select(Document.current_version_id).where(Document.id == doc.id)))
        .scalars()
        .all()
    )
    assert approved == [v2.id]


async def test_approve_non_approvable_status_rejected(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    await ctx.svc.approve(ctx.project, doc, v1.id, ctx.actor_id)
    # Re-approving an already-approved version is not a valid transition.
    with pytest.raises(InvalidDocumentState):
        await ctx.svc.approve(ctx.project, doc, v1.id, ctx.actor_id)


async def test_approve_unknown_version_404(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    with pytest.raises(NotFound):
        await ctx.svc.approve(ctx.project, doc, uuid.uuid4(), ctx.actor_id)


async def test_get_document_cross_project_is_404(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    with pytest.raises(NotFound):
        await ctx.svc.get_document(uuid.uuid4(), doc.id)


# ---------------------------------------------------------------------------
# audit trail (§CLAUDE.md §1.5)
# ---------------------------------------------------------------------------


async def test_mutations_write_audit_rows(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    doc = await _doc(ctx)
    v1 = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, "one", base_version_id=None, change_summary=None
    )
    await ctx.svc.approve(ctx.project, doc, v1.id, ctx.actor_id)
    actions = (
        (await db_session.execute(select(AuditEntry.action).order_by(AuditEntry.action)))
        .scalars()
        .all()
    )
    assert "document.created" in actions
    assert "document.version.created" in actions
    assert "document.version.approved" in actions
