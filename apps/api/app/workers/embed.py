"""arq job: chunk + embed a document version (M1.T2.3).

The worker opens its own session per job (§CLAUDE.md §4.1) and pulls the shared
embedding client from the job context (installed in ``on_startup``). The real DB
+ embedding work lives in :func:`app.ai.pipeline.run_chunk_and_embed`; this is a
thin arq wrapper so the logic stays unit-testable without Redis.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.ai.embeddings import EmbeddingClient, LiteLLMEmbeddingClient
from app.ai.pipeline import run_chunk_and_embed
from app.db import session_scope

EMBED_JOB = "chunk_and_embed"


async def chunk_and_embed(ctx: dict[str, Any], version_id: str) -> int:
    """Chunk and embed the given document version. Returns chunks embedded."""
    client: EmbeddingClient = ctx["embedding_client"]
    async with session_scope() as db:
        embedded = await run_chunk_and_embed(db, client, uuid.UUID(version_id))
        await db.commit()
    return embedded


async def on_startup(ctx: dict[str, Any]) -> None:
    ctx["embedding_client"] = LiteLLMEmbeddingClient()
