"""lineage_chunks: scope returned chunks to the focus item's project

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-14

# SRS anchors: FR-4.1.3, NFR-5.2.8
# LLD anchors: docs/krititva-lld.md §5.3
# Review finding: cross-project chunk leak (defense-in-depth)

Defense-in-depth for the tenant boundary: the 0011 ``lineage_chunks`` walked
``derived_from`` edges to chunks with no ``project_id`` predicate, so a link to a
foreign chunk (now blocked at the service layer) would still surface another
project's document content. This constrains the returned chunks to documents in
the focus item's own project.
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_SCOPED = """
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
JOIN document_versions dv ON dv.id = c.version_id
JOIN documents d ON d.id = dv.document_id
WHERE d.project_id = (SELECT project_id FROM work_items WHERE id = _focus)
ORDER BY ch.depth ASC;
$$ LANGUAGE SQL STABLE;
"""

# The 0011 body, restored verbatim on downgrade (no project scoping).
_UNSCOPED = """
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
    op.execute(_SCOPED)


def downgrade() -> None:
    op.execute(_UNSCOPED)
