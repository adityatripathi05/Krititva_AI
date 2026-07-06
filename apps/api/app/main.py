"""FastAPI application factory.

Route modules mount incrementally as M0 milestones land. This scaffold ships
health probes only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routes import health
from app.config import get_settings
from app.db import dispose_engine


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
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
    # Health probes live at the root (unversioned) so probes don't break on version bumps.
    app.include_router(health.router)
    return app


app = create_app()


def main() -> None:
    """Entrypoint for `krititva-api` script."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)  # noqa: S104
