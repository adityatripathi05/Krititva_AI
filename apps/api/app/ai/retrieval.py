"""Semantic retrieval over document chunks (FR-4.5.6, NFR-5.1.3).

The candidate set is scoped to a project's **current approved** document versions
(joined through ``documents.current_version_id``) and to chunks embedded with the
requested model — drafts and stale versions are never retrieved. Ranking is
cosine distance against the query vector, served by the partial HNSW index.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentVersion
from app.models.enums import DocType


async def semantic_search(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    doc_types: Sequence[DocType],
    embedding_model: str,
    query_vec: Sequence[float],
    k: int = 20,
    exclude_ids: Sequence[uuid.UUID] = (),
) -> list[DocumentChunk]:
    """Return the ``k`` nearest chunks to ``query_vec`` within the project's
    approved documents of the given ``doc_types``, embedded with ``embedding_model``."""
    if not doc_types or k <= 0:
        return []
    stmt = (
        select(DocumentChunk)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(
            Document.project_id == project_id,
            Document.doc_type.in_(list(doc_types)),
            DocumentChunk.embedding_model == embedding_model,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(list(query_vec)))
        .limit(k)
    )
    if exclude_ids:
        stmt = stmt.where(DocumentChunk.id.not_in(list(exclude_ids)))
    return list((await db.execute(stmt)).scalars().all())
