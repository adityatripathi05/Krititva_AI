"""ai_generation_jobs + ai_provenance; resolve work_items/document_versions FKs

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-13

# SRS anchors: FR-4.6.2-4.6.10, FR-4.6.4 (provenance), NFR-5.3.1-5.3.2
# LLD anchors: docs/krititva-lld.md §2.2 (AI jobs, provenance), §2.3
# Roadmap task: M1.T3.1

Creates the enums agent_role / artifact_type / job_status, the
ai_generation_jobs table (mutable during a run; append-only after finished_at,
§CLAUDE.md §1.3), and the append-only ai_provenance ledger (§1.2). Resolves the
last two deferred cross-module FKs against ai_generation_jobs:
  - work_items.source_job_id      -> ai_generation_jobs(id)   (plain since 0006)
  - document_versions.ai_job_id   -> ai_generation_jobs(id)   (plain since 0008)

ai_generation_jobs is project-scoped (org context flows through project_id), so
it carries no organization_id — see feedback-project-scoped-no-org-id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_AGENT_ROLE = ("project_owner", "architect", "scrum_master", "developer", "qa")
_ARTIFACT_TYPE = (
    "srs",
    "epic_breakdown",
    "hld",
    "lld",
    "sprint_plan",
    "story_breakdown",
    "task_breakdown",
    "api_contract",
    "test_plan",
    "test_cases",
)
_JOB_STATUS = ("queued", "running", "awaiting_review", "accepted", "rejected", "failed")


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # ---- enums first ---------------------------------------------------
    op.execute(f"CREATE TYPE agent_role AS ENUM {_sql_values(_AGENT_ROLE)}")
    op.execute(f"CREATE TYPE artifact_type AS ENUM {_sql_values(_ARTIFACT_TYPE)}")
    op.execute(f"CREATE TYPE job_status AS ENUM {_sql_values(_JOB_STATUS)}")

    # ---- ai_generation_jobs --------------------------------------------
    op.create_table(
        "ai_generation_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_role", _enum("agent_role", *_AGENT_ROLE), nullable=False),
        sa.Column("target_artifact", _enum("artifact_type", *_ARTIFACT_TYPE), nullable=False),
        sa.Column("focus_item_id", sa.Uuid(), sa.ForeignKey("work_items.id"), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "status", _enum("job_status", *_JOB_STATUS), nullable=False, server_default="queued"
        ),
        sa.Column("retrieval_model", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "result_document_version",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_jobs_project_status", "ai_generation_jobs", ["project_id", "status"]
    )
    op.create_index(
        "idx_jobs_running_heartbeat",
        "ai_generation_jobs",
        ["heartbeat_at"],
        postgresql_where=sa.text("status = 'running'"),
    )

    # ---- ai_provenance (append-only ledger, §1.2/§1.3) -----------------
    op.create_table(
        "ai_provenance",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("ai_generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column(
            "source_chunk",
            sa.Uuid(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chunk_hash", sa.Text(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column(
            "source_item",
            sa.Uuid(),
            sa.ForeignKey("work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "stage IN ('lineage', 'semantic', 'operational')", name="ck_provenance_stage"
        ),
        sa.CheckConstraint(
            "source_chunk IS NOT NULL OR source_item IS NOT NULL", name="ck_provenance_source"
        ),
    )
    op.create_index("idx_provenance_job", "ai_provenance", ["job_id"])

    # ---- resolve deferred cross-module FKs -----------------------------
    op.create_foreign_key(
        "fk_wi_source_job", "work_items", "ai_generation_jobs", ["source_job_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_dv_ai_job", "document_versions", "ai_generation_jobs", ["ai_job_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_dv_ai_job", "document_versions", type_="foreignkey")
    op.drop_constraint("fk_wi_source_job", "work_items", type_="foreignkey")
    op.drop_index("idx_provenance_job", table_name="ai_provenance")
    op.drop_table("ai_provenance")
    op.drop_index("idx_jobs_running_heartbeat", table_name="ai_generation_jobs")
    op.drop_index("idx_jobs_project_status", table_name="ai_generation_jobs")
    op.drop_table("ai_generation_jobs")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS artifact_type")
    op.execute("DROP TYPE IF EXISTS agent_role")


def _sql_values(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"({joined})"
