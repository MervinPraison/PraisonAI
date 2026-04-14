"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..db.base import init_db
from .routes.activity import router as activity_router
from .routes.agents import router as agents_router
from .routes.auth import router as auth_router
from .routes.dependencies import router as dependencies_router
from .routes.issues import router as issues_router
from .routes.labels import router as labels_router
from .routes.projects import router as projects_router
from .routes.workspaces import router as workspaces_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: init DB on startup."""
    await init_db()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PraisonAI Platform",
        version="0.1.0",
        description="Workspace, auth, issues, and projects for PraisonAI agents",
        lifespan=lifespan,
    )
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(workspaces_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(issues_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(labels_router, prefix="/api/v1")
    app.include_router(dependencies_router, prefix="/api/v1")
    app.include_router(activity_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
