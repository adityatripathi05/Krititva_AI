"""documents + document_versions (immutable, append-only version chain)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-13

# SRS anchors: FR-4.5.1-4.5.4, FR-4.5.7-4.5.9, FR-4.10.4
# LLD anchors: docs/krititva-lld.md §2.2 (Documents), §2.3 (migration ordering)
# Roadmap task: M1.T1.1

Ordering (LLD §2.3):
  - Enums (doc_type, doc_status) created first.
  - documents and document_versions created without the circular FK.
  - fk_current_version (documents.current_version_id -> document_versions.id)
    added after both tables exist, resolving the documents ↔ document_versions
    cycle.
  - idx_doc_one_approved: partial UNIQUE index enforcing at most one 'approved'
    version per document (M1.T1.3 single-approved invariant).

Deferred cross-module FK now resolvable (target lands here):
  - stale_flags.triggered_by -> document_versions(id)  (created plain in 0006)

document_versions is append-only (§CLAUDE.md §1.3): it has no updated_at column.
document_versions.ai_job_id stays a plain UUID until ai_generation_jobs lands in
M1.T3 (fk_dv_ai_job).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_DOC_TYPE = ("srs", "hld", "lld", "test_plan", "other")
_DOC_STATUS = ("draft", "in_review", "approved", "superseded")


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an already-created Postgres ENUM type."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # ---- enums first ---------------------------------------------------
    op.execute("CREATE TYPE doc_type AS ENUM ('srs', 'hld', 'lld', 'test_plan', 'other')")
    op.execute(
        "CREATE TYPE doc_status AS ENUM ('draft', 'in_review', 'approved', 'superseded')"
    )

    # ---- documents (current_version_id FK added after versions exist) --
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", _enum("doc_type", *_DOC_TYPE), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),  # FK added below
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("idx_documents_project", "documents", ["project_id"])

    # ---- document_versions (append-only: no updated_at) ----------------
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "status", _enum("doc_status", *_DOC_STATUS), nullable=False, server_default="draft"
        ),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ai_job_id", sa.Uuid(), nullable=True),  # FK deferred (M1.T3)
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "version_no", name="uq_doc_versions_doc_no"),
    )
    op.create_index("idx_doc_versions_document", "document_versions", ["document_id"])

    # ---- resolve the documents ↔ document_versions FK cycle ------------
    op.create_foreign_key(
        "fk_current_version",
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
    )

    # ---- single-approved-per-document invariant (M1.T1.3) --------------
    op.create_index(
        "idx_doc_one_approved",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    # ---- resolve deferred FK: stale_flags.triggered_by -----------------
    op.create_foreign_key(
        "fk_stale_triggered_by",
        "stale_flags",
        "document_versions",
        ["triggered_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_stale_triggered_by", "stale_flags", type_="foreignkey")
    op.drop_index("idx_doc_one_approved", table_name="document_versions")
    op.drop_constraint("fk_current_version", "documents", type_="foreignkey")
    op.drop_index("idx_doc_versions_document", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("idx_documents_project", table_name="documents")
    op.drop_table("documents")
    op.execute("DROP TYPE IF EXISTS doc_status")
    op.execute("DROP TYPE IF EXISTS doc_type")
