"""
Server for PraisonAI Async Jobs API.

Provides FastAPI application setup and server startup.
"""

import logging
import os
import threading
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .store import InMemoryJobStore, JobStore, SqliteJobStore
from .executor import JobExecutor
from .router import create_router

logger = logging.getLogger(__name__)

# Process-default instances, used only when create_app() is not given its own
# store/executor (and by the kanban jobs bridge). Never overwritten by create_app.
_store: Optional[JobStore] = None
_executor: Optional[JobExecutor] = None
_store_lock = threading.Lock()
_executor_lock = threading.Lock()


def _build_default_store() -> JobStore:
    """Select the default job store backend.

    Persist to SQLite when ``PRAISONAI_JOBS_DB_PATH`` is set so job state and
    idempotency keys survive restarts (retries then correctly de-duplicate).
    Fall back to the in-memory store only for local dev, and refuse to start
    with it in production so a deployment cannot silently lose idempotency.
    """
    db_path = os.environ.get("PRAISONAI_JOBS_DB_PATH")
    if db_path:
        logger.info("Jobs API using persistent SQLite store: %s", db_path)
        return SqliteJobStore(path=db_path)
    if os.environ.get("ENVIRONMENT") == "production":
        raise RuntimeError(
            "Jobs API refused to start with the in-memory store in production. "
            "Set PRAISONAI_JOBS_DB_PATH (e.g. /var/lib/praisonai/jobs.db) to "
            "persist jobs and idempotency keys across restarts, or explicitly "
            "pass store=InMemoryJobStore() to create_app()."
        )
    logger.warning(
        "Jobs API using in-memory store - jobs and idempotency keys are LOST "
        "on restart. Set PRAISONAI_JOBS_DB_PATH to persist across restarts."
    )
    return InMemoryJobStore(max_jobs=1000)


def get_store() -> JobStore:
    """Get or create the job store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _build_default_store()
    return _store


def _build_executor(store: JobStore) -> JobExecutor:
    return JobExecutor(
        store=store,
        max_concurrent=int(os.environ.get("PRAISONAI_MAX_CONCURRENT_JOBS", "10")),
        default_timeout=int(os.environ.get("PRAISONAI_JOB_TIMEOUT", "3600"))
    )


def get_executor() -> JobExecutor:
    """Get or create the job executor."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = _build_executor(get_store())
    return _executor


def _arrived_off_loopback(request) -> bool:
    """True when the request (or ASGI scope) reached a non-loopback local socket address."""
    import ipaddress

    server = getattr(request, "scope", request).get("server")
    try:
        ip = ipaddress.ip_address(server[0])
    except (TypeError, ValueError, IndexError):
        return False  # unix socket or in-process client: no network address
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return not ip.is_loopback


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    executor = app.state.job_executor
    await executor.start()
    logger.info("Jobs API server started")
    try:
        yield
    finally:
        await executor.stop()
        logger.info("Jobs API server stopped")


def create_app(
    store: Optional[JobStore] = None,
    executor: Optional[JobExecutor] = None,
    cors_origins: Optional[list] = None
) -> FastAPI:
    """
    Create the FastAPI application.
    
    Args:
        store: Optional custom job store
        executor: Optional custom executor
        cors_origins: Optional list of allowed CORS origins
        
    Returns:
        FastAPI application
    """
    # Each app owns its store/executor; process defaults are used only when
    # nothing is injected, so building a second app never rewires the first.
    if store is None and executor is None:
        store, executor = get_store(), get_executor()
    elif executor is None:
        executor = _build_executor(store)
    elif store is None:
        store = executor.store

    app = FastAPI(
        title="PraisonAI Jobs API",
        description="Async Jobs API for long-running agent tasks",
        version="1.0.0",
        lifespan=lifespan
    )
    app.state.job_store = store
    app.state.job_executor = executor
    
    # Add CORS middleware with secure defaults
    if cors_origins is None:
        # Default secure origins based on environment
        default_origins = os.getenv("JOBS_CORS_ORIGINS", "").split(",")
        default_origins = [origin.strip() for origin in default_origins if origin.strip() and origin.strip() != "*"]
        
        if not default_origins:
            # Secure defaults for different environments
            if os.getenv("ENVIRONMENT") == "production":
                origins = []  # No origins allowed in production without explicit config
            else:
                origins = [
                    "http://localhost:3000",   # Development frontend
                    "http://localhost:8000",   # Local development
                    "http://127.0.0.1:3000",   # Local development
                    "http://127.0.0.1:8000",   # Local development
                ]
        else:
            origins = default_origins
    else:
        origins = cors_origins
    
    if origins:  # Only add CORS middleware if origins are specified
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            # Never pair credentials with "*" (Starlette reflects the Origin).
            allow_credentials="*" not in origins,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Origin", "Accept", "Idempotency-Key"],
        )

    jobs_api_key = os.environ.get("PRAISONAI_JOBS_API_KEY")

    if jobs_api_key:
        from praisonai._api_auth import build_api_key_middleware

        app.add_middleware(build_api_key_middleware(jobs_api_key, {"/health"}))
    else:
        from starlette.responses import JSONResponse

        # One keyless rule for start_server() and ``uvicorn ...:create_app
        # --factory``: answer only when the declared bind is loopback (the
        # factory declares nothing, so it needs a key or a declared loopback
        # PRAISONAI_JOBS_BIND_HOST) and the request reached a loopback address.
        declared = os.environ.get("PRAISONAI_JOBS_BIND_HOST", "")
        declared_local = declared in ("127.0.0.1", "localhost", "::1")

        class JobsAuthRequiredMiddleware:
            # Plain ASGI, not BaseHTTPMiddleware: that one runs the endpoint in a
            # separate task, which stalls background job submission on Python 3.10.
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] == "lifespan" or scope.get("path") == "/health" or (
                    declared_local and not _arrived_off_loopback(scope)
                ):
                    return await self.app(scope, receive, send)
                if scope["type"] != "http":
                    return await send({"type": "websocket.close", "code": 1008})
                await JSONResponse(
                    {"error": "PRAISONAI_JOBS_API_KEY required (or serve on a declared "
                              "loopback bind: PRAISONAI_JOBS_BIND_HOST=127.0.0.1)"},
                    status_code=401,
                )(scope, receive, send)

        app.add_middleware(JobsAuthRequiredMiddleware)
        logger.warning(
            "Jobs API has no PRAISONAI_JOBS_API_KEY: any local process can submit "
            "jobs to this server. Set PRAISONAI_JOBS_API_KEY on shared hosts."
        )

    # Add jobs router
    jobs_router = create_router(store, executor)
    app.include_router(jobs_router)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "store": store.__class__.__name__,
            "executor_stats": executor.get_stats()
        }
    
    # Stats endpoint
    @app.get("/stats")
    async def get_stats():
        """Get server statistics."""
        stats = {
            "executor": executor.get_stats()
        }
        
        if hasattr(store, "get_stats"):
            stats["store"] = store.get_stats()
        
        return stats
    
    return app


def start_server(
    host: str = "127.0.0.1",
    port: int = 8005,
    reload: bool = False,
    workers: int = 1,
    log_level: str = "info"
):
    """
    Start the jobs API server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload for development
        workers: Number of worker processes
        log_level: Logging level
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is required. Install with: pip install uvicorn")
    
    from praisonaiagents.agent.launch_security import require_bind_token

    require_bind_token(
        host, os.environ.get("PRAISONAI_JOBS_API_KEY"), server="Jobs API",
        hint="Set PRAISONAI_JOBS_API_KEY",
    )
    logger.info(f"Starting PraisonAI Jobs API on {host}:{port}")
    os.environ["PRAISONAI_JOBS_BIND_HOST"] = host
    
    uvicorn.run(
        "praisonai.jobs.server:create_app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
        factory=True
    )


# For direct module execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PraisonAI Jobs API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8005, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    parser.add_argument("--log-level", default="info", help="Log level")
    
    args = parser.parse_args()
    
    start_server(
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level=args.log_level
    )
