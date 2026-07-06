"""Alembic environment. Advisory-lock protects concurrent api-replica startups.

Real ORM models are imported here in M0.T2 so autogen has metadata; for now,
metadata=None keeps offline mode functional.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Fill sqlalchemy.url from settings so operators do not duplicate it in
# alembic.ini — but only when the caller has not overridden it (e.g. tests
# passing a testcontainer URL via Config.set_main_option).
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)

# Import models so Base.metadata is populated; used by tests that reconstruct
# schema and (optionally) by --autogenerate. Migrations themselves are still
# hand-authored per the krititva-migration skill.
from app.models import Base

target_metadata: Any = Base.metadata

ADVISORY_LOCK_KEY = "krititva-migrations"


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        # Transaction-scoped advisory lock: auto-released on COMMIT or ROLLBACK.
        # Concurrent api-replica starts serialize here; the migration itself
        # runs inside the same transaction.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable: AsyncEngine = create_async_engine(
        config.get_main_option("sqlalchemy.url") or "",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
