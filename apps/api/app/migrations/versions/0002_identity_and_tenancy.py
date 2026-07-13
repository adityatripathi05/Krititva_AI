"""identity + tenancy: organizations, users, invitations, clients, projects, project_members

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

# SRS anchors: FR-4.1.1-4.1.7, FR-4.2.1-4.2.6
# LLD anchors: docs/krititva-lld.md §2.2 (Tenancy & identity, Projects & methodology)
# Roadmap task: M0.T2.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an already-created Postgres ENUM type.

    Use ``postgresql.ENUM`` (not ``sa.Enum``): the SA generic-Enum path emits a
    stray CREATE TYPE inside ``op.create_table`` even with ``create_type=False``
    on some SQLAlchemy versions. The Postgres-dialect ENUM does the right thing.
    """
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # ---- organizations -------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ---- users ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "org_role",
            _enum("org_role", "org_admin", "member"),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("tz", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_org", "users", ["organization_id"])

    # ---- clients -------------------------------------------------------
    op.create_table(
        "clients",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "contact_json",
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
    op.create_index("idx_clients_org", "clients", ["organization_id"])

    # ---- projects ------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id"),
            nullable=True,
        ),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "methodology",
            _enum("methodology", "agile", "waterfall", "hybrid"),
            nullable=False,
        ),
        sa.Column(
            "ai_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "llm_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "client_portal_mode",
            _enum("portal_mode", "none", "export_only", "portal"),
            nullable=False,
            server_default="export_only",
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('active','on_hold','completed','cancelled')",
            name="ck_projects_status",
        ),
    )
    op.create_index("idx_projects_org", "projects", ["organization_id"])
    op.create_index("idx_projects_client", "projects", ["client_id"])

    # ---- project_members ----------------------------------------------
    op.create_table(
        "project_members",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role",
            _enum(
                "project_role",
                "project_owner",
                "scrum_master",
                "developer",
                "qa",
                "viewer",
                "client_approver",
            ),
            nullable=False,
        ),
        sa.Column(
            "allocation_pct",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "allocation_pct BETWEEN 0 AND 100",
            name="ck_project_members_allocation",
        ),
    )

    # ---- invitations ---------------------------------------------------
    op.create_table(
        "invitations",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "invited_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id"),
            nullable=True,
        ),
        sa.Column(
            "project_role",
            _enum(
                "project_role",
                "project_owner",
                "scrum_master",
                "developer",
                "qa",
                "viewer",
                "client_approver",
            ),
            nullable=True,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "state",
            _enum(
                "invitation_state",
                "pending",
                "accepted",
                "revoked",
                "expired",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_user",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index("idx_invitations_email", "invitations", ["email"])
    op.create_index(
        "idx_invitations_state",
        "invitations",
        ["state"],
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_invitations_state", table_name="invitations")
    op.drop_index("idx_invitations_email", table_name="invitations")
    op.drop_table("invitations")

    op.drop_table("project_members")

    op.drop_index("idx_projects_client", table_name="projects")
    op.drop_index("idx_projects_org", table_name="projects")
    op.drop_table("projects")

    op.drop_index("idx_clients_org", table_name="clients")
    op.drop_table("clients")

    op.drop_index("idx_users_org", table_name="users")
    op.drop_table("users")

    op.drop_table("organizations")
