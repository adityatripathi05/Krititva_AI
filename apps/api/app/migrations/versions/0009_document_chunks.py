"""document_chunks with discriminated embeddings + HNSW indexes

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-13

# SRS anchors: FR-4.5.4-4.5.6, NFR-5.1.3, NFR-5.1.5
# LLD anchors: docs/krititva-lld.md §2.2 (document_chunks), §HLD 5.4
# Roadmap task: M1.T2.1

Creates the pgvector extension (first use in the schema), the append-only
document_chunks table with discriminated embedding columns (primary 768-dim +
optional alt 1536-dim, each tagged by model), and partial HNSW indexes.

Deferred cross-module FK now resolvable (target lands here):
  - work_item_links.to_chunk -> document_chunks(id)  (created plain in 0006)

LLD-internal reconciliation: §2.1 delta note (4) says embedding_model is NOT
NULL, but the definitive DDL block in §2.2 lists it nullable. The nullable form
is required by the chunk-then-embed flow — the chunker inserts rows before the
embedding worker computes vectors — so this follows the §2.2 DDL. embedding and
embedding_model are written together by the worker.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_alt", Vector(1536), nullable=True),
        sa.Column("embedding_alt_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("idx_chunks_version", "document_chunks", ["version_id"])

    # Partial HNSW indexes (m=16, ef_construction=64) — only rows that have a
    # vector are indexed (CLAUDE.md §6.5, LLD §2.2).
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64) "
        "WHERE embedding IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_chunks_embedding_alt ON document_chunks "
        "USING hnsw (embedding_alt vector_cosine_ops) WITH (m = 16, ef_construction = 64) "
        "WHERE embedding_alt IS NOT NULL"
    )

    # ---- resolve deferred FK: work_item_links.to_chunk -----------------
    op.create_foreign_key(
        "fk_link_chunk",
        "work_item_links",
        "document_chunks",
        ["to_chunk"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_link_chunk", "work_item_links", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_alt")
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.drop_index("idx_chunks_version", table_name="document_chunks")
    op.drop_table("document_chunks")
    # The vector extension is intentionally NOT dropped — shared, like pgcrypto.
