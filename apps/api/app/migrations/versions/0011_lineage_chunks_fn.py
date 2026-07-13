"""lineage_chunks SQL function (cycle-safe derived_from walk to chunks)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-13

# SRS anchors: FR-4.6.9, FR-4.10.2
# LLD anchors: docs/krititva-lld.md §2.2 (Lineage helper), §5.3
# Roadmap task: M1.T4.1

Deferred from M0.T5 because its body JOINs document_chunks, which did not exist
until M1.T2. Walks ``derived_from`` work-item edges from a focus item (cycle-safe
via a visited array, depth-bounded) and returns the document chunks those items
link to, shallowest first.
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_CREATE = """
CREATE OR REPLACE FUNCTION lineage_chunks(_focus UUID, _max_depth INT DEFAULT 6)
RETURNS TABLE(chunk_id UUID, section_path TEXT, content TEXT, depth INT) AS $$
WITH RECURSIVE walk(item_id, depth, visited) AS (
    SELECT _focus, 0, ARRAY[_focus]::UUID[]
    UNION ALL
    SELECT l.to_item, w.depth + 1, w.visited || l.to_item
    FROM walk w
    JOIN work_item_links l ON l.from_item = w.item_id
    WHERE l.link_type = 'derived_from'
      AND l.to_item IS NOT NULL
      AND NOT (l.to_item = ANY(w.visited))
      AND w.depth < _max_depth
),
chunks AS (
    SELECT DISTINCT l.to_chunk AS chunk_id, w.depth
    FROM walk w
    JOIN work_item_links l ON l.from_item = w.item_id
    WHERE l.link_type = 'derived_from' AND l.to_chunk IS NOT NULL
)
SELECT c.id, c.section_path, c.content, ch.depth
FROM chunks ch
JOIN document_chunks c ON c.id = ch.chunk_id
ORDER BY ch.depth ASC;
$$ LANGUAGE SQL STABLE;
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS lineage_chunks(UUID, INT)")
