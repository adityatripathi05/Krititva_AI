"""extensions + enums for identity, tenancy, and projects

Revision ID: 0001
Revises:
Create Date: 2026-07-06

# SRS anchors: FR-4.1.4, FR-4.1.5, FR-4.2.3, FR-4.2.5, FR-4.3.1
# LLD anchors: docs/krititva-lld.md §2.2 (Enumerations block)
# Roadmap task: M0.T2.2
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute("CREATE TYPE org_role AS ENUM ('org_admin', 'member')")
    op.execute(
        "CREATE TYPE project_role AS ENUM ("
        "'project_owner', 'scrum_master', 'developer', "
        "'qa', 'viewer', 'client_approver')"
    )
    op.execute("CREATE TYPE methodology AS ENUM ('agile', 'waterfall', 'hybrid')")
    op.execute("CREATE TYPE portal_mode AS ENUM ('none', 'export_only', 'portal')")
    op.execute(
        "CREATE TYPE invitation_state AS ENUM "
        "('pending', 'accepted', 'revoked', 'expired')"
    )


def downgrade() -> None:
    op.execute("DROP TYPE IF EXISTS invitation_state")
    op.execute("DROP TYPE IF EXISTS portal_mode")
    op.execute("DROP TYPE IF EXISTS methodology")
    op.execute("DROP TYPE IF EXISTS project_role")
    op.execute("DROP TYPE IF EXISTS org_role")
    # Extensions are intentionally NOT dropped — shared with future migrations.
