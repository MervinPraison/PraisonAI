"""
Background Job Manager for PraisonAI Agents.

Provides job lifecycle tracking, auto-backgrounding based on threshold,
and status inspection for long-running agent tasks.
"""

import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
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
    # Terminal state assigned during startup reconciliation to a job that was
    # ``RUNNING`` when its process died. The work was abandoned by the crash;
    # ``LOST`` records that fact so the job is queryable rather than silently
    # vanishing (see :meth:`BackgroundJobManager.reconcile_on_start`).
    LOST = "lost"


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
    # Whether the terminal result has been delivered back to ``origin`` via the
    # ``on_complete`` callback. Used by restart reconciliation to distinguish a
    # job that COMPLETED-and-was-delivered from one that COMPLETED-but-whose
    # deliver-back never fired (e.g. the process died between recording the
    # result and running the callback). Only meaningful when a store persists
    # ``JobInfo`` across restarts; ``False`` preserves prior behaviour.
    delivered: bool = False

    @property
    def duration(self) -> Optional[float]:
        """Get job duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or time.time()
        return end_time - self.started_at


@runtime_checkable
class BackgroundJobStore(Protocol):
    """Persistence contract for durable background jobs.

    Mirrors the store-protocol pattern used elsewhere in the SDK (e.g. the
    session/scheduler stores): the core runner stays heavy-import-free and a
    concrete SQLite implementation lives in the wrapper/bot layer alongside the
    other durable stores (``OutboundQueue``, DLQ, approvals). Injecting a store
    is entirely opt-in — when none is supplied the runner behaves exactly as the
    original pure in-memory implementation.

    Implementations must be safe to call from the runner's worker threads.
    """

    def upsert(self, job: JobInfo) -> None:
        """Insert or update the persisted record for ``job`` (keyed by id)."""
        ...

    def get(self, job_id: str) -> Optional[JobInfo]:
        """Return the persisted :class:`JobInfo`, or ``None`` if unknown."""
        ...

    def list_unreconciled(self) -> List[JobInfo]:
        """Return jobs needing reconciliation after a restart.

        Specifically: jobs left ``PENDING`` or ``RUNNING`` at the last write
        (their process died before or during the run — both are orphaned and
        reconciled to ``LOST``) and jobs ``COMPLETED`` with an ``origin`` that
        were never marked ``delivered``. Returned in a stable order for
        deterministic replay.
        """
        ...


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
        *,
        store: Optional[BackgroundJobStore] = None,
    ):
        """
        Initialize the background job manager.
        
        Args:
            max_workers: Maximum number of concurrent background jobs
            auto_background_threshold: Time in seconds after which a job
                should be automatically backgrounded
            store: Optional durable :class:`BackgroundJobStore`. When supplied,
                every job state transition is persisted so jobs survive a
                process restart and can be reconciled via
                :meth:`reconcile_on_start`. When ``None`` (the default) the
                runner is pure in-memory exactly as before — zero overhead, no
                behaviour change.
        """
        self.max_workers = max_workers
        self.auto_background_threshold = auto_background_threshold
        self._store = store
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, JobInfo] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    def _persist(self, job: JobInfo) -> None:
        """Best-effort persist of a job's current state to the store.

        A persistence failure must never crash a worker thread or lose the
        in-memory job, so exceptions are swallowed and logged. No-op when no
        store is configured (the default), keeping the hot path free.
        """
        if self._store is None:
            return
        try:
            self._store.upsert(job)
        except Exception as e:  # noqa: BLE001 — persistence must never crash worker
            logger.debug(
                "Persisting job %s failed (non-fatal): %s", job.job_id, e,
            )
    
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
        # Persist the PENDING record before it starts so a crash between spawn
        # and first run still leaves a recoverable trace (reconciled as LOST).
        self._persist(job_info)
        
        def _fire_complete() -> None:
            if on_complete is None:
                return
            with self._lock:
                info = self._jobs.get(job_id)
            if info is None:
                return
            try:
                on_complete(info)
                # Record successful deliver-back so restart reconciliation does
                # not re-deliver an already-delivered result.
                with self._lock:
                    info.delivered = True
                self._persist(info)
            except Exception as e:  # noqa: BLE001 — delivery must never crash worker
                logger.debug(
                    "on_complete callback for job %s raised (non-fatal): %s",
                    job_id, e,
                )

        def _run_job():
            with self._lock:
                job = self._jobs[job_id]
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
            self._persist(job)
            
            try:
                result = func()
                with self._lock:
                    job = self._jobs[job_id]
                    job.status = JobStatus.COMPLETED
                    job.completed_at = time.time()
                    job.result = result
                self._persist(job)
                _fire_complete()
                return result
            except Exception as e:
                with self._lock:
                    job = self._jobs[job_id]
                    job.status = JobStatus.FAILED
                    job.completed_at = time.time()
                    job.error = str(e)
                self._persist(job)
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
            if job_id in self._jobs:
                return self._jobs[job_id].status
        job = self._store.get(job_id) if self._store else None
        if job is None:
            raise KeyError(f"Job {job_id} not found")
        return job.status
    
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
            if job_id in self._jobs:
                return self._jobs[job_id]
        job = self._store.get(job_id) if self._store else None
        if job is None:
            raise KeyError(f"Job {job_id} not found")
        return job
    
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
                job = self._jobs[job_id]
            else:
                job = None
        if job is not None:
            self._persist(job)
        return cancelled

    def reconcile_on_start(
        self,
        redeliver: Optional[Callable[[JobInfo], Any]] = None,
    ) -> Dict[str, int]:
        """Reconcile persisted jobs after a process restart.

        Closes the durability gap where a restart mid-job silently drops work
        and its deferred deliver-back. For every job the store reports as
        unreconciled:

        - A job left ``RUNNING`` when its process died is marked
          :attr:`JobStatus.LOST` (a terminal, queryable state) and persisted.
          The abandoned work is not automatically re-run — that decision is
          left to the caller, who can inspect ``LOST`` jobs and re-submit.
        - A job that ``COMPLETED`` with an ``origin`` but was never
          ``delivered`` has ``redeliver`` invoked with its :class:`JobInfo`,
          re-firing the deliver-back-to-origin the crash interrupted. On a
          successful redeliver the job is marked ``delivered`` and persisted so
          it is not delivered twice on the next restart.

        Every persisted job is also re-hydrated into this manager's in-memory
        map so it remains queryable by id after the restart.

        No-op (returns zero counts) when no store is configured. Safe to call
        once at startup, mirroring ``OutboundQueue.drain`` wiring.

        Args:
            redeliver: Callable invoked with a COMPLETED-but-undelivered
                :class:`JobInfo` to replay its deliver-back. Best-effort — an
                exception it raises is logged and the job is left undelivered
                for a future retry, never crashing startup. When ``None``,
                undelivered jobs are re-hydrated but not delivered.

        Returns:
            Counts dict: ``{"lost": n, "redelivered": n, "rehydrated": n}``.
        """
        counts = {"lost": 0, "redelivered": 0, "rehydrated": 0}
        if self._store is None:
            return counts

        try:
            unreconciled = list(self._store.list_unreconciled())
        except Exception as e:  # noqa: BLE001 — reconciliation must never crash startup
            logger.warning("Listing unreconciled jobs failed: %s", e)
            return counts

        for job in unreconciled:
            # A job left RUNNING (or still PENDING) when its process died was
            # orphaned by the crash. Transition it to the terminal LOST state
            # *before* it becomes visible in the in-memory map, so a concurrent
            # get_status never observes the transient RUNNING/PENDING status the
            # caller is specifically reconciling away. Stamp completed_at so the
            # terminal record is age-evictable by cleanup_completed().
            orphaned = job.status in (JobStatus.RUNNING, JobStatus.PENDING)
            if orphaned:
                prior_status = job.status.value
                job.status = JobStatus.LOST
                if job.completed_at is None:
                    job.completed_at = time.time()

            with self._lock:
                self._jobs[job.job_id] = job
            counts["rehydrated"] += 1

            if orphaned:
                self._persist(job)
                counts["lost"] += 1
                logger.info(
                    "Reconciled orphaned %s job %s as LOST",
                    prior_status, job.job_id,
                )
            elif (
                job.status == JobStatus.COMPLETED
                and job.origin
                and not job.delivered
            ):
                if redeliver is None:
                    continue
                try:
                    redeliver(job)
                    job.delivered = True
                    self._persist(job)
                    counts["redelivered"] += 1
                    logger.info(
                        "Re-delivered undelivered completed job %s to origin",
                        job.job_id,
                    )
                except Exception as e:  # noqa: BLE001 — redeliver is best-effort
                    logger.warning(
                        "Re-delivery for job %s failed (will retry next "
                        "restart): %s", job.job_id, e,
                    )

        return counts

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
    
    # Terminal states whose in-memory records are age-evictable. LOST is
    # included so reconciled orphans (see reconcile_on_start) do not accumulate
    # unbounded across restarts — without it every restart would leak a fresh
    # batch of LOST entries for the process lifetime.
    _EVICTABLE_STATES = (
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.LOST,
    )

    def cleanup_completed(self, max_age: float = 3600.0) -> int:
        """
        Remove terminal jobs older than max_age seconds.
        
        Args:
            max_age: Maximum age in seconds for terminal jobs
            
        Returns:
            Number of jobs removed
        """
        now = time.time()
        removed = 0
        
        with self._lock:
            to_remove = []
            for job_id, info in self._jobs.items():
                if info.status in self._EVICTABLE_STATES:
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
