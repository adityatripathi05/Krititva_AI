"""FastAPI application factory.

Route modules mount incrementally as M0 milestones land. This scaffold ships
health probes only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.responses import ORJSONResponse

from app import __version__
from app.api.deps import enforce_org_rate_limit
from app.api.errors import register_exception_handlers
from app.api.routes import artifacts, auth, documents, health, projects, work_items
from app.config import get_settings
from app.db import dispose_engine
from app.queue import create_arq_pool
from app.security.csrf import CSRFMiddleware

_log = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        app.state.arq_pool = await create_arq_pool()
    except Exception as exc:  # degrade gracefully if Redis is down
        app.state.arq_pool = None
        _log.warning("arq_pool_unavailable", error=str(exc))
    try:
        yield
    finally:
        pool = getattr(app.state, "arq_pool", None)
        if pool is not None:
            await pool.close()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Krititva AI",
        version=__version__,
        description="Open-source project management for software agencies.",
        default_response_class=ORJSONResponse,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
        lifespan=_lifespan,
    )
    register_exception_handlers(app)
    app.add_middleware(CSRFMiddleware)
    # Per-org RPS applies to the authenticated resource routers. Health is an
    # unauthenticated probe; auth mixes public endpoints (login/setup) with no org
    # context, so it is excluded from the org-keyed limit.
    rate_limited = [Depends(enforce_org_rate_limit)]
    # Health probes live at the root (unversioned) so probes don't break on version bumps.
    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(projects.router, prefix=settings.api_prefix, dependencies=rate_limited)
    app.include_router(work_items.router, prefix=settings.api_prefix, dependencies=rate_limited)
    app.include_router(documents.router, prefix=settings.api_prefix, dependencies=rate_limited)
    app.include_router(artifacts.router, prefix=settings.api_prefix, dependencies=rate_limited)
    return app


app = create_app()


def main() -> None:
    """Entrypoint for `krititva-api` script."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)  # noqa: S104
