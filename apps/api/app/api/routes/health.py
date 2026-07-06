"""Liveness and readiness probes (FR-4.12, NFR-5.3.1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, Any]:
    """Process is up. No external checks."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Ready to serve — database round-trip succeeds."""
    result = await db.execute(text("SELECT 1"))
    ok = result.scalar_one() == 1
    return {"status": "ok" if ok else "degraded", "version": __version__}
