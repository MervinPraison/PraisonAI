"""
Job Models for PraisonAI Async Jobs API.

Defines the data structures for job submission, status, and results.
"""

import uuid
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a job."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobSubmitRequest(BaseModel):
    """Request body for submitting a new job."""
    prompt: str = Field(..., description="The prompt or task for the agent")
    agent_file: Optional[str] = Field(None, description="Path to agents.yaml file")
    agent_yaml: Optional[str] = Field(None, description="Inline agent YAML configuration")
    recipe_name: Optional[str] = Field(None, description="Recipe name to execute (mutually exclusive with agent_file)")
    recipe_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Recipe configuration overrides")
    framework: Optional[str] = Field("praisonai", description="Framework to use (praisonai, crewai, autogen)")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional configuration")
    webhook_url: Optional[str] = Field(None, description="URL to POST results when complete")
    timeout: Optional[int] = Field(3600, description="Timeout in seconds (default: 1 hour)")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key to prevent duplicate submissions")
    idempotency_scope: Optional[str] = Field("none", description="Idempotency scope: none, session, global")


class JobSubmitResponse(BaseModel):
    """Response after submitting a job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    created_at: datetime = Field(..., description="Job creation timestamp")
    poll_url: str = Field(..., description="URL to poll for status")
    stream_url: str = Field(..., description="URL for SSE streaming")


class JobProgress(BaseModel):
    """Progress information for a running job."""
    percentage: float = Field(0.0, ge=0.0, le=100.0, description="Completion percentage")
    current_step: Optional[str] = Field(None, description="Current step description")
    steps_completed: int = Field(0, description="Number of steps completed")
    steps_total: Optional[int] = Field(None, description="Total number of steps")


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    progress: JobProgress = Field(default_factory=JobProgress, description="Progress information")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="When job started running")
    completed_at: Optional[datetime] = Field(None, description="When job completed")
    agent_id: Optional[str] = Field(None, description="Current agent ID")
    run_id: Optional[str] = Field(None, description="Run ID for tracing")
    session_id: Optional[str] = Field(None, description="Session ID")
    error: Optional[str] = Field(None, description="Error message if failed")
    retry_after: Optional[int] = Field(None, description="Suggested seconds before next poll")


class JobResultResponse(BaseModel):
    """Response for job result query."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Final job status")
    result: Optional[Any] = Field(None, description="Job result/output")
    result_url: Optional[str] = Field(None, description="URL to fetch large results")
    metrics: Optional[Dict[str, Any]] = Field(None, description="Execution metrics")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="When job started running")
    completed_at: Optional[datetime] = Field(None, description="When job completed")
    duration_seconds: Optional[float] = Field(None, description="Total execution time")
    error: Optional[str] = Field(None, description="Error message if failed")


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: List[JobStatusResponse] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total number of jobs matching filter")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Number of jobs per page")


class Job(BaseModel):
    """Internal job representation with full state."""
    id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    status: JobStatus = Field(default=JobStatus.QUEUED)
    
    # Request data
    prompt: str = Field(...)
    agent_file: Optional[str] = Field(None)
    agent_yaml: Optional[str] = Field(None)
    recipe_name: Optional[str] = Field(None)
    recipe_config: Dict[str, Any] = Field(default_factory=dict)
    framework: str = Field("praisonai")
    config: Dict[str, Any] = Field(default_factory=dict)
    webhook_url: Optional[str] = Field(None)
    timeout: int = Field(3600)
    session_id: Optional[str] = Field(None)
    idempotency_key: Optional[str] = Field(None)
    idempotency_scope: str = Field("none")
    
    # Progress tracking
    progress_percentage: float = Field(0.0)
    progress_step: Optional[str] = Field(None)
    steps_completed: int = Field(0)
    steps_total: Optional[int] = Field(None)
    
    # Attribution
    agent_id: Optional[str] = Field(None)
    run_id: Optional[str] = Field(None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    
    # Result
    result: Optional[Any] = Field(None)
    error: Optional[str] = Field(None)
    metrics: Optional[Dict[str, Any]] = Field(None)
    
    # Internal
    _cancel_requested: bool = False
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()
    
    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)
    
    def to_status_response(self, base_url: str = "") -> JobStatusResponse:
        """Convert to status response."""
        retry_after = None
        if self.status == JobStatus.QUEUED:
            retry_after = 2
        elif self.status == JobStatus.RUNNING:
            retry_after = 5
        
        return JobStatusResponse(
            job_id=self.id,
            status=self.status,
            progress=JobProgress(
                percentage=self.progress_percentage,
                current_step=self.progress_step,
                steps_completed=self.steps_completed,
                steps_total=self.steps_total
            ),
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            agent_id=self.agent_id,
            run_id=self.run_id,
            session_id=self.session_id,
            error=self.error,
            retry_after=retry_after
        )
    
    def to_result_response(self) -> JobResultResponse:
        """Convert to result response."""
        return JobResultResponse(
            job_id=self.id,
            status=self.status,
            result=self.result,
            result_url=None,  # For large results, would be set
            metrics=self.metrics,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_seconds=self.duration_seconds,
            error=self.error
        )
    
    def start(self):
        """Mark job as started."""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def succeed(self, result: Any, metrics: Optional[Dict[str, Any]] = None):
        """Mark job as succeeded."""
        self.status = JobStatus.SUCCEEDED
        self.result = result
        self.metrics = metrics
        self.completed_at = datetime.utcnow()
        self.progress_percentage = 100.0
    
    def fail(self, error: str):
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = datetime.utcnow()
    
    def cancel(self):
        """Mark job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        self._cancel_requested = True
    
    def update_progress(
        self,
        percentage: Optional[float] = None,
        step: Optional[str] = None,
        steps_completed: Optional[int] = None,
        steps_total: Optional[int] = None
    ):
        """Update job progress."""
        if percentage is not None:
            self.progress_percentage = min(max(percentage, 0.0), 100.0)
        if step is not None:
            self.progress_step = step
        if steps_completed is not None:
            self.steps_completed = steps_completed
        if steps_total is not None:
            self.steps_total = steps_total
