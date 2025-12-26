"""
Async Jobs API for PraisonAI.

Provides HTTP API endpoints for long-running agent tasks:
- Submit jobs (POST /api/v1/runs)
- Check status (GET /api/v1/runs/{job_id})
- Get results (GET /api/v1/runs/{job_id}/result)
- Cancel jobs (POST /api/v1/runs/{job_id}/cancel)
- Stream progress (GET /api/v1/runs/{job_id}/stream)

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Server only starts when explicitly requested
- No overhead when not in use

Usage:
    # Start the jobs server
    praisonai serve --port 8005
    
    # Or programmatically
    from praisonai.jobs import start_server
    start_server(port=8005)
"""

__all__ = [
    # Models
    "Job",
    "JobStatus",
    "JobSubmitRequest",
    "JobStatusResponse",
    "JobResultResponse",
    # Store
    "JobStore",
    "InMemoryJobStore",
    # Executor
    "JobExecutor",
    # Router
    "create_router",
    # Server
    "start_server",
    "create_app",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name in ("Job", "JobStatus", "JobSubmitRequest", "JobStatusResponse", "JobResultResponse"):
        from .models import Job, JobStatus, JobSubmitRequest, JobStatusResponse, JobResultResponse
        return locals()[name]
    
    if name in ("JobStore", "InMemoryJobStore"):
        from .store import JobStore, InMemoryJobStore
        return locals()[name]
    
    if name == "JobExecutor":
        from .executor import JobExecutor
        return JobExecutor
    
    if name == "create_router":
        from .router import create_router
        return create_router
    
    if name in ("start_server", "create_app"):
        from .server import start_server, create_app
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
