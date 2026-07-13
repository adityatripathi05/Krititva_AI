"""force C collation on work_items.rank so lexorank ordering is bytewise

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07

# SRS anchors: FR-4.4.7
# LLD anchors: docs/krititva-lld.md §2.2 (work_items.rank)
# Roadmap task: M0 review fix (#1)

Lexorank keys are only correct under bytewise ordering (0-9 < A-Z < a-z). A plain
``TEXT`` column inherits the database collation (``en_US.utf8`` on the shipped
pgvector image), under which ``'a' < 'Z'`` — the inverse — so ``ORDER BY rank``
mis-sorts and ``MAX(rank)`` picks the wrong key, letting ``_append_rank`` mint a
duplicate rank. Pinning the column to ``COLLATE "C"`` makes every comparison,
sort, and aggregate on it bytewise, matching the algorithm.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE work_items ALTER COLUMN rank TYPE text COLLATE "C"')


def downgrade() -> None:
    op.execute('ALTER TABLE work_items ALTER COLUMN rank TYPE text COLLATE pg_catalog."default"')
