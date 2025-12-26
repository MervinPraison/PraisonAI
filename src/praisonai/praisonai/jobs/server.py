"""
Server for PraisonAI Async Jobs API.

Provides FastAPI application setup and server startup.
"""

import logging
import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .store import InMemoryJobStore, JobStore
from .executor import JobExecutor
from .router import create_router

logger = logging.getLogger(__name__)

# Global instances (for single-process deployment)
_store: Optional[JobStore] = None
_executor: Optional[JobExecutor] = None


def get_store() -> JobStore:
    """Get or create the job store."""
    global _store
    if _store is None:
        _store = InMemoryJobStore(max_jobs=1000)
    return _store


def get_executor() -> JobExecutor:
    """Get or create the job executor."""
    global _executor
    if _executor is None:
        _executor = JobExecutor(
            store=get_store(),
            max_concurrent=int(os.environ.get("PRAISONAI_MAX_CONCURRENT_JOBS", "10")),
            default_timeout=int(os.environ.get("PRAISONAI_JOB_TIMEOUT", "3600"))
        )
    return _executor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    executor = get_executor()
    await executor.start()
    logger.info("Jobs API server started")
    
    yield
    
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
    global _store, _executor
    
    if store:
        _store = store
    if executor:
        _executor = executor
    
    app = FastAPI(
        title="PraisonAI Jobs API",
        description="Async Jobs API for long-running agent tasks",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    origins = cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add jobs router
    jobs_router = create_router(get_store(), get_executor())
    app.include_router(jobs_router)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "store": get_store().__class__.__name__,
            "executor_stats": get_executor().get_stats()
        }
    
    # Stats endpoint
    @app.get("/stats")
    async def get_stats():
        """Get server statistics."""
        store = get_store()
        executor = get_executor()
        
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
    
    logger.info(f"Starting PraisonAI Jobs API on {host}:{port}")
    
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
