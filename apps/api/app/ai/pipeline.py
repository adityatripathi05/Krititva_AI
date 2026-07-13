"""Chunk-and-embed pipeline core (FR-4.5.4-4.5.6).

The heavy lifting behind the ``chunk_and_embed`` arq job, factored out of the
worker wrapper so it can be driven directly in tests with a real session and a
:class:`~app.ai.embeddings.FakeEmbeddingClient`. Idempotent: chunking happens
once per version, and only chunks still lacking a vector are (re-)embedded, so a
retried job never duplicates rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chunking import chunk_markdown
from app.ai.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingClient
from app.models import DocumentChunk, DocumentVersion

EMBED_BATCH = 32


async def run_chunk_and_embed(
    db: AsyncSession,
    client: EmbeddingClient,
    version_id: uuid.UUID,
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> int:
    """Chunk ``version_id``'s markdown (once) and embed any chunks missing a
    vector. Returns the number of chunks embedded this run."""
    version = await db.get(DocumentVersion, version_id)
    if version is None:
        return 0

    existing = (
        await db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.version_id == version_id)
        )
    ).scalar_one()
    if existing == 0:
        for spec in chunk_markdown(version.content_md):
            db.add(
                DocumentChunk(
                    version_id=version_id,
                    section_path=spec.section_path,
                    content=spec.content,
                    content_hash=spec.content_hash,
                    token_count=spec.token_count,
                )
            )
        await db.flush()

    pending = list(
        (
            await db.execute(
                select(DocumentChunk)
                .where(
                    DocumentChunk.version_id == version_id,
                    DocumentChunk.embedding.is_(None),
                )
                .order_by(DocumentChunk.id)
            )
        )
        .scalars()
        .all()
    )

    embedded = 0
    for start in range(0, len(pending), EMBED_BATCH):
        batch = pending[start : start + EMBED_BATCH]
        vectors = await client.embed([c.content for c in batch], model)
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = model
            embedded += 1
        await db.flush()

    return embedded
