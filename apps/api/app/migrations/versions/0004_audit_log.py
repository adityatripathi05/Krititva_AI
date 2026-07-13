"""append-only audit_log (FR-4.10.1)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

# SRS anchors: FR-4.10.1, FR-4.10.3, FR-4.10.4
# LLD anchors: docs/krititva-lld.md §2.2 (Audit)
# Roadmap task: M0.T3 (needed alongside auth to satisfy CLAUDE.md §1.5)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_audit_project_time",
        "audit_log",
        ["project_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_audit_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_index("idx_audit_action", table_name="audit_log")
    op.drop_index("idx_audit_project_time", table_name="audit_log")
    op.drop_table("audit_log")
