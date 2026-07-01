"""
Background Job Manager for PraisonAI Agents.

Provides job lifecycle tracking, auto-backgrounding based on threshold,
and status inspection for long-running agent tasks.
"""

import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Status of a background job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobInfo:
    """Information about a background job."""
    job_id: str
    status: JobStatus
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    # Optional origin/delivery context captured at spawn time so a gateway
    # can route the result back to the originating conversation on completion
    # (mirrors the scheduler's ``deliver="origin"`` grammar). Empty by default,
    # preserving the pull-only behaviour when no delivery target is set.
    origin: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> Optional[float]:
        """Get job duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or time.time()
        return end_time - self.started_at


class BackgroundJobManager:
    """
    Manages background jobs for agent tasks.
    
    Features:
    - Job lifecycle tracking (pending, running, completed, failed)
    - Auto-backgrounding based on execution time threshold
    - Thread-safe job status inspection
    - Configurable thread pool for concurrent execution
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        auto_background_threshold: float = 5.0,
    ):
        """
        Initialize the background job manager.
        
        Args:
            max_workers: Maximum number of concurrent background jobs
            auto_background_threshold: Time in seconds after which a job
                should be automatically backgrounded
        """
        self.max_workers = max_workers
        self.auto_background_threshold = auto_background_threshold
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, JobInfo] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
    
    @property
    def active_jobs(self) -> int:
        """Get the number of active (pending or running) jobs."""
        with self._lock:
            return sum(
                1 for job in self._jobs.values()
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )
    
    def start_job(
        self,
        func: Callable[[], Any],
        job_id: Optional[str] = None,
        on_complete: Optional[Callable[["JobInfo"], None]] = None,
        origin: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a new background job.
        
        Args:
            func: The function to execute in the background
            job_id: Optional custom job ID (auto-generated if not provided)
            on_complete: Optional callback invoked with the terminal
                :class:`JobInfo` once the job reaches a terminal state
                (completed or failed). This is the observable completion
                signal a gateway subscribes to in order to proactively
                deliver a background result back to the originating chat
                without an active turn. Best-effort — any exception it
                raises is swallowed so a delivery failure never crashes the
                worker thread. Defaults to ``None`` (pull-only behaviour).
            origin: Optional origin/delivery context (e.g. ``platform``,
                ``chat_id``, ``thread_id``, ``session_id``, ``deliver``)
                stored on the :class:`JobInfo` so ``on_complete`` can route
                the result. Empty/omitted preserves today's behaviour.
            
        Returns:
            The job ID
        """
        job_id = job_id or str(uuid.uuid4())[:8]
        
        job_info = JobInfo(
            job_id=job_id,
            status=JobStatus.PENDING,
            origin=dict(origin) if origin else {},
        )
        
        with self._lock:
            self._jobs[job_id] = job_info
        
        def _fire_complete() -> None:
            if on_complete is None:
                return
            with self._lock:
                info = self._jobs.get(job_id)
            if info is None:
                return
            try:
                on_complete(info)
            except Exception as e:  # noqa: BLE001 — delivery must never crash worker
                logger.debug(
                    "on_complete callback for job %s raised (non-fatal): %s",
                    job_id, e,
                )

        def _run_job():
            with self._lock:
                self._jobs[job_id].status = JobStatus.RUNNING
                self._jobs[job_id].started_at = time.time()
            
            try:
                result = func()
                with self._lock:
                    self._jobs[job_id].status = JobStatus.COMPLETED
                    self._jobs[job_id].completed_at = time.time()
                    self._jobs[job_id].result = result
                _fire_complete()
                return result
            except Exception as e:
                with self._lock:
                    self._jobs[job_id].status = JobStatus.FAILED
                    self._jobs[job_id].completed_at = time.time()
                    self._jobs[job_id].error = str(e)
                _fire_complete()
                raise
        
        future = self._executor.submit(_run_job)
        with self._lock:
            self._futures[job_id] = future
        
        return job_id
    
    def get_status(self, job_id: str) -> JobStatus:
        """
        Get the status of a job.
        
        Args:
            job_id: The job ID to check
            
        Returns:
            The job status
            
        Raises:
            KeyError: If job_id is not found
        """
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job {job_id} not found")
            return self._jobs[job_id].status
    
    def get_job_info(self, job_id: str) -> JobInfo:
        """
        Get full information about a job.
        
        Args:
            job_id: The job ID to check
            
        Returns:
            The job information
            
        Raises:
            KeyError: If job_id is not found
        """
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job {job_id} not found")
            return self._jobs[job_id]
    
    def get_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """
        Get the result of a completed job.
        
        Args:
            job_id: The job ID
            timeout: Maximum time to wait for completion
            
        Returns:
            The job result
            
        Raises:
            KeyError: If job_id is not found
            TimeoutError: If timeout is reached before completion
            RuntimeError: If job failed
        """
        with self._lock:
            if job_id not in self._futures:
                raise KeyError(f"Job {job_id} not found")
            future = self._futures[job_id]
        
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Attempt to cancel a job.
        
        Args:
            job_id: The job ID to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        with self._lock:
            if job_id not in self._futures:
                return False
            future = self._futures[job_id]
            cancelled = future.cancel()
            if cancelled:
                self._jobs[job_id].status = JobStatus.CANCELLED
                self._jobs[job_id].completed_at = time.time()
            return cancelled
    
    def list_jobs(self, status: Optional[JobStatus] = None) -> Dict[str, JobInfo]:
        """
        List all jobs, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            Dictionary of job_id -> JobInfo
        """
        with self._lock:
            if status is None:
                return dict(self._jobs)
            return {
                job_id: info
                for job_id, info in self._jobs.items()
                if info.status == status
            }
    
    def cleanup_completed(self, max_age: float = 3600.0) -> int:
        """
        Remove completed jobs older than max_age seconds.
        
        Args:
            max_age: Maximum age in seconds for completed jobs
            
        Returns:
            Number of jobs removed
        """
        now = time.time()
        removed = 0
        
        with self._lock:
            to_remove = []
            for job_id, info in self._jobs.items():
                if info.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    if info.completed_at and (now - info.completed_at) > max_age:
                        to_remove.append(job_id)
            
            for job_id in to_remove:
                del self._jobs[job_id]
                if job_id in self._futures:
                    del self._futures[job_id]
                removed += 1
        
        return removed
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the job manager.
        
        Args:
            wait: Whether to wait for pending jobs to complete
        """
        self._executor.shutdown(wait=wait)


# Global job manager instance (lazy initialized)
_global_job_manager: Optional[BackgroundJobManager] = None
_global_lock = threading.Lock()


def get_job_manager() -> BackgroundJobManager:
    """Get the global job manager instance."""
    global _global_job_manager
    with _global_lock:
        if _global_job_manager is None:
            _global_job_manager = BackgroundJobManager()
        return _global_job_manager
