"""FastAPI request dependencies.

Real auth/RBAC dependencies land in M0.T3. This module currently exposes the
database session dependency only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. See CLAUDE.md §4.1."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


__all__ = ["get_db"]
