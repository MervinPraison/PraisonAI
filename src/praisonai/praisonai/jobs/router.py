"""
FastAPI Router for PraisonAI Async Jobs API.

Provides HTTP endpoints for job management.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header, Request, Query, Response
from sse_starlette.sse import EventSourceResponse

from .models import (
    Job,
    JobStatus,
    JobSubmitRequest,
    JobSubmitResponse,
    JobStatusResponse,
    JobResultResponse,
    JobListResponse
)
from .store import JobStore
from .executor import JobExecutor

logger = logging.getLogger(__name__)


def create_router(store: JobStore, executor: JobExecutor) -> APIRouter:
    """
    Create the jobs API router.
    
    Args:
        store: Job storage backend
        executor: Job executor
        
    Returns:
        FastAPI router with all endpoints
    """
    router = APIRouter(prefix="/api/v1/runs", tags=["jobs"])
    
    @router.post("", response_model=JobSubmitResponse, status_code=202)
    async def submit_job(
        request: Request,
        response: Response,
        body: JobSubmitRequest,
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
    ):
        """
        Submit a new job for execution.
        
        Returns 202 Accepted with job ID and status URLs.
        Headers returned:
        - Location: URL to poll for status
        - Retry-After: Suggested seconds before first poll (default: 2)
        
        If an Idempotency-Key header is provided and a job with that key
        already exists, returns the existing job instead of creating a new one.
        """
        # Check idempotency key
        effective_key = idempotency_key or body.idempotency_key
        if effective_key:
            existing = await store.get_by_idempotency_key(effective_key)
            if existing:
                logger.info(f"Returning existing job for idempotency key: {effective_key}")
                base_url = str(request.base_url).rstrip("/")
                poll_url = f"{base_url}/api/v1/runs/{existing.id}"
                response.headers["Location"] = poll_url
                response.headers["Retry-After"] = "2"
                return JobSubmitResponse(
                    job_id=existing.id,
                    status=existing.status,
                    created_at=existing.created_at,
                    poll_url=poll_url,
                    stream_url=f"{base_url}/api/v1/runs/{existing.id}/stream"
                )
        
        # Create new job
        job = Job(
            prompt=body.prompt,
            agent_file=body.agent_file,
            agent_yaml=body.agent_yaml,
            framework=body.framework or "praisonai",
            config=body.config or {},
            webhook_url=body.webhook_url,
            timeout=body.timeout or 3600,
            session_id=body.session_id,
            idempotency_key=effective_key
        )
        
        # Submit for execution
        await executor.submit(job)
        
        # Build response with Location and Retry-After headers (RFC best practice)
        base_url = str(request.base_url).rstrip("/")
        poll_url = f"{base_url}/api/v1/runs/{job.id}"
        response.headers["Location"] = poll_url
        response.headers["Retry-After"] = "2"
        
        return JobSubmitResponse(
            job_id=job.id,
            status=job.status,
            created_at=job.created_at,
            poll_url=poll_url,
            stream_url=f"{base_url}/api/v1/runs/{job.id}/stream"
        )
    
    @router.get("", response_model=JobListResponse)
    async def list_jobs(
        status: Optional[str] = Query(None, description="Filter by status"),
        session_id: Optional[str] = Query(None, description="Filter by session ID"),
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Jobs per page")
    ):
        """
        List jobs with optional filters.
        """
        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = JobStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}"
                )
        
        # Get jobs
        offset = (page - 1) * page_size
        jobs = await store.list_jobs(
            status=status_filter,
            session_id=session_id,
            limit=page_size,
            offset=offset
        )
        
        total = await store.count(status=status_filter, session_id=session_id)
        
        return JobListResponse(
            jobs=[job.to_status_response() for job in jobs],
            total=total,
            page=page,
            page_size=page_size
        )
    
    @router.get("/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(job_id: str):
        """
        Get the status of a job.
        
        Returns current status, progress, and timing information.
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        return job.to_status_response()
    
    @router.get("/{job_id}/result", response_model=JobResultResponse)
    async def get_job_result(job_id: str):
        """
        Get the result of a completed job.
        
        Returns 409 Conflict if job is not yet complete.
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if not job.is_terminal:
            raise HTTPException(
                status_code=409,
                detail=f"Job is not complete. Current status: {job.status.value}"
            )
        
        return job.to_result_response()
    
    @router.post("/{job_id}/cancel", response_model=JobStatusResponse)
    async def cancel_job(job_id: str):
        """
        Cancel a running job.
        
        Returns 409 Conflict if job is already complete.
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if job.is_terminal:
            raise HTTPException(
                status_code=409,
                detail=f"Job is already complete. Status: {job.status.value}"
            )
        
        success = await executor.cancel(job_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to cancel job")
        
        # Refresh job state
        job = await store.get(job_id)
        return job.to_status_response()
    
    @router.delete("/{job_id}", status_code=204)
    async def delete_job(job_id: str):
        """
        Delete a job.
        
        Only completed jobs can be deleted.
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if not job.is_terminal:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a running job. Cancel it first."
            )
        
        await store.delete(job_id)
    
    @router.get("/{job_id}/stream")
    async def stream_job(job_id: str):
        """
        Stream job progress via Server-Sent Events (SSE).
        
        Events:
        - status: Job status updates
        - progress: Progress percentage updates
        - result: Final result (when complete)
        - error: Error message (when failed)
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        async def event_generator():
            """Generate SSE events for job progress."""
            last_status = None
            last_progress = -1
            
            # Register for progress updates
            progress_queue = asyncio.Queue()
            
            async def on_progress(updated_job: Job):
                await progress_queue.put(updated_job)
            
            executor.register_progress_callback(job_id, on_progress)
            
            try:
                while True:
                    # Get current job state
                    current_job = await store.get(job_id)
                    if not current_job:
                        yield {
                            "event": "error",
                            "data": '{"error": "Job not found"}'
                        }
                        break
                    
                    # Send status update if changed
                    if current_job.status != last_status:
                        last_status = current_job.status
                        yield {
                            "event": "status",
                            "data": f'{{"status": "{current_job.status.value}", "job_id": "{job_id}"}}'
                        }
                    
                    # Send progress update if changed
                    if current_job.progress_percentage != last_progress:
                        last_progress = current_job.progress_percentage
                        yield {
                            "event": "progress",
                            "data": f'{{"percentage": {current_job.progress_percentage}, "step": "{current_job.progress_step or ""}"}}'
                        }
                    
                    # Check if complete
                    if current_job.is_terminal:
                        if current_job.status == JobStatus.SUCCEEDED:
                            result_str = str(current_job.result).replace('"', '\\"')[:1000]
                            yield {
                                "event": "result",
                                "data": f'{{"result": "{result_str}"}}'
                            }
                        elif current_job.status == JobStatus.FAILED:
                            error_str = (current_job.error or "Unknown error").replace('"', '\\"')
                            yield {
                                "event": "error",
                                "data": f'{{"error": "{error_str}"}}'
                            }
                        elif current_job.status == JobStatus.CANCELLED:
                            yield {
                                "event": "cancelled",
                                "data": '{"message": "Job was cancelled"}'
                            }
                        break
                    
                    # Wait for next update or timeout
                    try:
                        await asyncio.wait_for(progress_queue.get(), timeout=5.0)
                    except asyncio.TimeoutError:
                        # Send heartbeat
                        yield {
                            "event": "heartbeat",
                            "data": f'{{"timestamp": "{datetime.utcnow().isoformat()}"}}'
                        }
            finally:
                executor.unregister_progress_callback(job_id)
        
        return EventSourceResponse(event_generator())
    
    return router
