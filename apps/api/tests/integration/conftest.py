"""Integration-test fixtures backed by a real Postgres via testcontainers.

Session scope:
- Postgres container spun up once per pytest session (image: pgvector/pgvector:pg16,
  driver: asyncpg).
- Alembic migrations applied to ``head`` once against that container.

Function scope:
- ``db_session`` opens a connection, begins an outer transaction, hands the test
  a ``AsyncSession`` with ``join_transaction_mode='create_savepoint'``. Tests may
  call ``session.commit()`` freely — only the outer transaction is rolled back on
  teardown, so state resets between tests without re-running migrations.

Every test in this package is marked ``integration`` and is excluded from the
default PR CI run.
"""

from __future__ import annotations

import os

# Disable the Ryuk reaper before testcontainers is imported. Ryuk relies on the
# Docker daemon exposing a random host port on its own container, which fails
# intermittently on Docker Desktop for Windows. Container cleanup still happens
# because the ``postgres_container`` fixture is a proper context manager.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration


API_DIR = Path(__file__).resolve().parents[2]  # apps/api/
ALEMBIC_DIR = API_DIR / "app" / "migrations"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    # Default psycopg2 driver is used only by testcontainers' sync readiness
    # probe. We rewrite the URL to asyncpg in `postgres_dsn` for actual use.
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def postgres_dsn(postgres_container: PostgresContainer) -> str:
    dsn: str = postgres_container.get_connection_url()
    # Guarantee asyncpg regardless of testcontainers default.
    if "+asyncpg" not in dsn:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://").replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
    return dsn


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(postgres_dsn: str) -> None:
    """Apply Alembic migrations against the shared container once per session."""
    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", postgres_dsn)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(loop_scope="session")
async def engine(postgres_dsn: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(postgres_dsn, pool_pre_ping=True, future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session bound to an outer connection-level transaction.

    Test-level ``session.commit()`` calls commit the inner SAVEPOINT only;
    teardown rollback wipes everything at the connection boundary.
    """
    connection = await engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await connection.close()
