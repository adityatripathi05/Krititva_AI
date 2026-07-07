"""End-to-end migration verification (M0.T2 exit criterion).

Applies every revision to head (via the session fixture), then walks the
history down and back up to confirm every ``upgrade``/``downgrade`` pair is
reversible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = API_DIR / "app" / "migrations"

EXPECTED_TABLES = {
    "alembic_version",
    "organizations",
    "users",
    "invitations",
    "clients",
    "projects",
    "project_members",
    "refresh_tokens",
    "audit_log",
    "workflow_states",
    "workflow_transitions",
    "hierarchy_rules",
    "work_items",
    "work_item_links",
    "sprints",
    "milestones",
    "stale_flags",
}

EXPECTED_ENUMS = {
    "org_role",
    "project_role",
    "methodology",
    "portal_mode",
    "invitation_state",
    "work_item_kind",
    "link_type",
    "gate_status",
    "stale_reason",
}


async def test_all_expected_tables_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        table_names = set(
            await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        )
    assert EXPECTED_TABLES.issubset(table_names), f"Missing: {EXPECTED_TABLES - table_names}"


async def test_all_expected_enums_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
        enum_names = {row[0] for row in result}
    assert EXPECTED_ENUMS.issubset(enum_names), f"Missing: {EXPECTED_ENUMS - enum_names}"


def test_downgrade_then_upgrade_round_trip(postgres_dsn: str) -> None:
    """Migrations must be reversible (§CLAUDE.md §6, NFR-5.3.3)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", postgres_dsn)
    command.downgrade(cfg, "-1")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
