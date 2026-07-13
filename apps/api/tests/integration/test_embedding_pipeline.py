"""Chunk+embed pipeline + semantic retrieval (M1.T2.3/T2.4, FR-4.5.5-4.5.6).

Real Postgres (pgvector) via testcontainers; the embedder is the offline
:class:`FakeEmbeddingClient` (real Ollama runs only in the smoke suite, §CLAUDE.md
§5). Exercises write-back, idempotency, and the approved-current-version +
embedding-model retrieval filters.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DEFAULT_EMBEDDING_MODEL, FakeEmbeddingClient
from app.ai.pipeline import run_chunk_and_embed
from app.ai.retrieval import semantic_search
from app.models import DocStatus, DocType, Document, DocumentChunk, OrgRole, Project
from app.services.audit import AuditSink
from app.services.documents import DocumentService
from tests.integration._factories import make_org, make_project, make_user

pytestmark = pytest.mark.integration

_MD = """\
# System SRS
Overview of the system.
## Authentication
Users log in with email and password.
## Reporting
Nightly reports are generated.
"""


class Ctx:
    def __init__(
        self, db: AsyncSession, svc: DocumentService, project: Project, actor_id: uuid.UUID
    ) -> None:
        self.db = db
        self.svc = svc
        self.project = project
        self.actor_id = actor_id


async def _ctx(db: AsyncSession) -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    project = await make_project(db, org)
    await db.flush()
    return Ctx(db, DocumentService(db, AuditSink(db)), project, admin.id)


async def _approved_version(
    ctx: Ctx, doc_type: DocType = DocType.srs
) -> tuple[Document, uuid.UUID]:
    doc = await ctx.svc.create(ctx.project, doc_type, "Doc", ctx.actor_id)
    v = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, _MD, base_version_id=None, change_summary=None
    )
    await ctx.svc.approve(ctx.project, doc, v.id, ctx.actor_id)
    return doc, v.id


async def _chunk_count(db: AsyncSession, version_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.version_id == version_id)
            )
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def test_chunk_and_embed_writes_vectors(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    _, version_id = await _approved_version(ctx)
    embedded = await run_chunk_and_embed(db_session, FakeEmbeddingClient(), version_id)
    assert embedded == 3  # SRS + Authentication + Reporting
    rows = list(
        (
            await db_session.execute(
                select(DocumentChunk).where(DocumentChunk.version_id == version_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    for row in rows:
        assert row.embedding is not None
        assert len(row.embedding) == 768
        assert row.embedding_model == DEFAULT_EMBEDDING_MODEL


async def test_chunk_and_embed_is_idempotent(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    _, version_id = await _approved_version(ctx)
    first = await run_chunk_and_embed(db_session, FakeEmbeddingClient(), version_id)
    second = await run_chunk_and_embed(db_session, FakeEmbeddingClient(), version_id)
    assert first == 3
    assert second == 0  # nothing left to embed
    assert await _chunk_count(db_session, version_id) == 3  # no duplicate rows


async def test_chunk_and_embed_missing_version_is_noop(db_session: AsyncSession) -> None:
    assert await run_chunk_and_embed(db_session, FakeEmbeddingClient(), uuid.uuid4()) == 0


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def test_semantic_search_returns_approved_chunks(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    _, version_id = await _approved_version(ctx)
    client = FakeEmbeddingClient()
    await run_chunk_and_embed(db_session, client, version_id)
    query_vec = (await client.embed(["how do users log in"], DEFAULT_EMBEDDING_MODEL))[0]

    results = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.srs],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        query_vec=query_vec,
        k=10,
    )
    assert len(results) == 3
    assert all(r.embedding_model == DEFAULT_EMBEDDING_MODEL for r in results)


async def test_semantic_search_filters_by_model(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    _, version_id = await _approved_version(ctx)
    await run_chunk_and_embed(db_session, FakeEmbeddingClient(), version_id)
    query_vec = (await FakeEmbeddingClient().embed(["q"], DEFAULT_EMBEDDING_MODEL))[0]

    results = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.srs],
        embedding_model="some-other-model",
        query_vec=query_vec,
        k=10,
    )
    assert results == []


async def test_semantic_search_excludes_unapproved_versions(db_session: AsyncSession) -> None:
    """A draft version is not the document's current_version, so its chunks —
    even if embedded — must not surface in retrieval."""
    ctx = await _ctx(db_session)
    doc = await ctx.svc.create(ctx.project, DocType.srs, "Draft doc", ctx.actor_id)
    v = await ctx.svc.create_version(
        ctx.project, doc, ctx.actor_id, _MD, base_version_id=None, change_summary=None
    )
    assert v.status is DocStatus.draft
    await run_chunk_and_embed(db_session, FakeEmbeddingClient(), v.id)
    query_vec = (await FakeEmbeddingClient().embed(["q"], DEFAULT_EMBEDDING_MODEL))[0]

    results = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.srs],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        query_vec=query_vec,
        k=10,
    )
    assert results == []


async def test_semantic_search_honors_exclude_and_doc_types(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    _, version_id = await _approved_version(ctx)
    client = FakeEmbeddingClient()
    await run_chunk_and_embed(db_session, client, version_id)
    query_vec = (await client.embed(["q"], DEFAULT_EMBEDDING_MODEL))[0]

    all_hits = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.srs],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        query_vec=query_vec,
        k=10,
    )
    excluded = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.srs],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        query_vec=query_vec,
        k=10,
        exclude_ids=[all_hits[0].id],
    )
    assert all_hits[0].id not in {r.id for r in excluded}
    assert len(excluded) == len(all_hits) - 1

    # Filtering by a doc_type the project has no documents for yields nothing.
    none = await semantic_search(
        db_session,
        project_id=ctx.project.id,
        doc_types=[DocType.hld],
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        query_vec=query_vec,
        k=10,
    )
    assert none == []
