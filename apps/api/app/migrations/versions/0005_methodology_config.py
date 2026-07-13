"""methodology config: work_item_kind enum, workflow_states, workflow_transitions, hierarchy_rules

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07

# SRS anchors: FR-4.3.1, FR-4.3.2, FR-4.3.3, FR-4.3.4, FR-4.3.5
# LLD anchors: docs/krititva-lld.md §2.2 (Methodology configuration)
# Roadmap task: M0.T4.1

These three tables are project-scoped (they hang off ``projects``, which carries
``organization_id``), not directly tenant-scoped, so they intentionally omit an
``organization_id`` column — matching LLD §2.2 exactly. The ``test_migrations``
suite diffs the applied schema against that DDL, so any extra column is drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an already-created Postgres ENUM type. See migration 0002."""
    return postgresql.ENUM(*values, name=name, create_type=False)


_PROJECT_ROLE = (
    "project_owner",
    "scrum_master",
    "developer",
    "qa",
    "viewer",
    "client_approver",
)
_WORK_ITEM_KIND = (
    "phase",
    "epic",
    "feature",
    "story",
    "task",
    "bug",
    "deliverable",
    "test_case",
)


def upgrade() -> None:
    # ---- enum first ----------------------------------------------------
    op.execute(
        "CREATE TYPE work_item_kind AS ENUM ("
        "'phase', 'epic', 'feature', 'story', "
        "'task', 'bug', 'deliverable', 'test_case')"
    )

    # ---- workflow_states -----------------------------------------------
    op.create_table(
        "workflow_states",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column(
            "sort_order",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.CheckConstraint(
            "category IN ('todo', 'in_progress', 'done')",
            name="ck_workflow_states_category",
        ),
        sa.UniqueConstraint("project_id", "key", name="uq_workflow_states_project_key"),
    )

    # ---- workflow_transitions ------------------------------------------
    op.create_table(
        "workflow_transitions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_state",
            sa.Uuid(),
            sa.ForeignKey("workflow_states.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_state",
            sa.Uuid(),
            sa.ForeignKey("workflow_states.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_hard_gate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "required_role",
            _enum("project_role", *_PROJECT_ROLE),
            nullable=True,
        ),
        sa.Column(
            "approval_quorum",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "project_id",
            "from_state",
            "to_state",
            name="uq_workflow_transitions_project_from_to",
        ),
    )

    # ---- hierarchy_rules -----------------------------------------------
    op.create_table(
        "hierarchy_rules",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "parent_kind",
            _enum("work_item_kind", *_WORK_ITEM_KIND),
            primary_key=True,
        ),
        sa.Column(
            "child_kind",
            _enum("work_item_kind", *_WORK_ITEM_KIND),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("hierarchy_rules")
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_states")
    op.execute("DROP TYPE IF EXISTS work_item_kind")
