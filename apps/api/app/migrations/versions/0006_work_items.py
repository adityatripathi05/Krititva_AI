"""work item engine: work_items, work_item_links, sprints, milestones, stale_flags

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07

# SRS anchors: FR-4.4.1-4.4.9
# LLD anchors: docs/krititva-lld.md §2.2 (Work items, Sprints & milestones, stale_flags)
# Roadmap task: M0.T5.1

Deferred cross-module FKs (targets land in M1, see LLD §2.3):
  - work_items.source_job_id   -> ai_generation_jobs(id)
  - work_item_links.to_chunk   -> document_chunks(id)
  - stale_flags.triggered_by   -> document_versions(id)
These are created as plain UUID columns now; the FK constraints are added by the
migration that creates their target tables.

LLD delta: idx_wi_assignee_open is specified in §2.2 with a subquery predicate
(`WHERE state_id IN (SELECT ...)`), which Postgres forbids in index predicates.
Replaced with a plain index on assignee_id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

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


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an already-created Postgres ENUM type. See migration 0002."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # ---- enums first ---------------------------------------------------
    op.execute(
        "CREATE TYPE link_type AS ENUM ('derived_from', 'tests', 'blocks', 'relates_to')"
    )
    op.execute(
        "CREATE TYPE gate_status AS ENUM ('pending', 'in_review', 'approved', 'rejected')"
    )
    op.execute(
        "CREATE TYPE stale_reason AS ENUM "
        "('chunk_removed', 'chunk_changed', 'chunk_added_upstream')"
    )

    # ---- sprints -------------------------------------------------------
    op.create_table(
        "sprints",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="planned"),
        sa.CheckConstraint("state IN ('planned', 'active', 'closed')", name="ck_sprints_state"),
        sa.CheckConstraint("ends_on > starts_on", name="ck_sprints_dates"),
    )
    op.create_index("idx_sprints_project", "sprints", ["project_id"])

    # ---- milestones ----------------------------------------------------
    op.create_table(
        "milestones",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phase_kind", _enum("work_item_kind", *_WORK_ITEM_KIND), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_hard_gate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "gate_status",
            _enum("gate_status", "pending", "in_review", "approved", "rejected"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("idx_milestones_project", "milestones", ["project_id"])

    # ---- work_items ----------------------------------------------------
    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _enum("work_item_kind", *_WORK_ITEM_KIND), nullable=False),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("acceptance_md", sa.Text(), nullable=True),
        sa.Column(
            "state_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_states.id"),
            nullable=False,
        ),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sprint_id", sa.Uuid(), sa.ForeignKey("sprints.id"), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), sa.ForeignKey("milestones.id"), nullable=True),
        sa.Column("story_points", sa.Numeric(5, 1), nullable=True),
        sa.Column("estimated_hours", sa.Numeric(7, 2), nullable=True),
        sa.Column("actual_hours", sa.Numeric(7, 2), nullable=True),
        sa.Column("rank", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_job_id", sa.Uuid(), nullable=True),  # FK deferred (M1)
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("project_id", "seq", name="uq_work_items_project_seq"),
    )
    op.create_index("idx_wi_project_state", "work_items", ["project_id", "state_id"])
    op.create_index("idx_wi_parent", "work_items", ["parent_id"])
    op.create_index("idx_wi_sprint", "work_items", ["sprint_id"])
    op.create_index("idx_wi_milestone", "work_items", ["milestone_id"])
    op.create_index("idx_wi_assignee", "work_items", ["assignee_id"])

    # ---- work_item_links -----------------------------------------------
    op.create_table(
        "work_item_links",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "from_item",
            sa.Uuid(),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_item",
            sa.Uuid(),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("to_chunk", sa.Uuid(), nullable=True),  # FK deferred (M1)
        sa.Column(
            "link_type",
            _enum("link_type", "derived_from", "tests", "blocks", "relates_to"),
            nullable=False,
        ),
        sa.CheckConstraint("from_item <> to_item", name="ck_links_no_self"),
        sa.CheckConstraint(
            "to_item IS NOT NULL OR to_chunk IS NOT NULL", name="ck_links_target"
        ),
    )
    op.create_index("idx_links_from_type", "work_item_links", ["from_item", "link_type"])
    op.create_index("idx_links_to_item", "work_item_links", ["to_item"])
    op.create_index("idx_links_to_chunk", "work_item_links", ["to_chunk"])

    # ---- stale_flags ---------------------------------------------------
    op.create_table(
        "stale_flags",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),  # FK deferred (M1)
        sa.Column(
            "reason",
            _enum("stale_reason", "chunk_removed", "chunk_changed", "chunk_added_upstream"),
            nullable=False,
        ),
        sa.Column(
            "detail_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "target_kind IN ('document', 'work_item')", name="ck_stale_target_kind"
        ),
    )
    op.create_index(
        "idx_stale_open",
        "stale_flags",
        ["project_id"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_stale_open", table_name="stale_flags")
    op.drop_table("stale_flags")

    op.drop_index("idx_links_to_chunk", table_name="work_item_links")
    op.drop_index("idx_links_to_item", table_name="work_item_links")
    op.drop_index("idx_links_from_type", table_name="work_item_links")
    op.drop_table("work_item_links")

    op.drop_index("idx_wi_assignee", table_name="work_items")
    op.drop_index("idx_wi_milestone", table_name="work_items")
    op.drop_index("idx_wi_sprint", table_name="work_items")
    op.drop_index("idx_wi_parent", table_name="work_items")
    op.drop_index("idx_wi_project_state", table_name="work_items")
    op.drop_table("work_items")

    op.drop_index("idx_milestones_project", table_name="milestones")
    op.drop_table("milestones")

    op.drop_index("idx_sprints_project", table_name="sprints")
    op.drop_table("sprints")

    op.execute("DROP TYPE IF EXISTS stale_reason")
    op.execute("DROP TYPE IF EXISTS gate_status")
    op.execute("DROP TYPE IF EXISTS link_type")
