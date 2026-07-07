"""Liveness and readiness probes (FR-4.12, NFR-5.3.1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, Any]:
    """Process is up. No external checks."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Ready to serve — database round-trip succeeds. Returns 503 when the DB is
    unreachable so orchestrators see an honest not-ready signal (NFR-5.3.1)."""
    try:
        ok = (await db.execute(text("SELECT 1"))).scalar_one() == 1
    except SQLAlchemyError:
        ok = False
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "version": __version__},
    )
