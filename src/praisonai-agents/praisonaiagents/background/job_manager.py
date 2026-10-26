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
from concurrent.futures import CancelledError, ThreadPoolExecutor, Future
from concurrent.futures import TimeoutError as FuturesTimeoutError

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
        reconciled to ``LOST``) and jobs ``COMPLETED`` or ``LOST`` with an
        ``origin`` that were never marked ``delivered``. Returned in a stable order for
        deterministic replay.
        """
        ...


def _emit_job_completed(info: "JobInfo") -> None:
    """Emit the JOB_COMPLETED hook for a job that reached a terminal state.

    Fired for every background job, not only the ones carrying a ``deliver``
    target: ``on_complete`` is a delivery callback the gateway may or may not
    install, whereas ``HookEvent.JOB_COMPLETED`` is the observability contract
    plugins subscribe to. Also fired once when restart reconciliation marks an
    orphaned job ``LOST``. Best-effort -- a missing hooks package or a raising
    subscriber never affects the job's own result.
    """
    try:
        from praisonaiagents.hooks import fire_hook

        fire_hook(
            "job_completed",
            {
                "job_id": info.job_id,
                "status": getattr(info.status, "value", str(info.status)),
                "result": info.result,
                "error": info.error,
                "agent_name": "background",
                "session_id": str(info.origin.get("session_id", "") or ""),
                "deliver": str(info.origin.get("deliver", "") or ""),
                "platform": str(info.origin.get("platform", "") or ""),
                "chat_id": str(info.origin.get("chat_id", "") or ""),
                "thread_id": str(info.origin.get("thread_id", "") or ""),
            },
        )
    except Exception as e:  # noqa: BLE001 - observability must not break the job
        logger.debug(
            "JOB_COMPLETED hook emit for job %s failed (non-fatal): %s",
            info.job_id, e,
        )


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
        self._last_gc = time.time()

    def _persist(self, job: JobInfo) -> None:
        """Best-effort persist of a job's current state to the store.

        A persistence failure must never crash a worker thread or lose the
        in-memory job, so exceptions are swallowed and logged. No-op when no
        store is configured (the default), keeping the hot path free.
        """
        if self._store is None:
            return
        # Check-and-write under the lock: a finished job whose id was reused
        # must not overwrite the newer job's persisted record.
        with self._lock:
            current = self._jobs.get(job.job_id)
            if current is not None and current is not job:
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

        Raises:
            ValueError: If ``job_id`` belongs to a job that is still pending
                or running. Ids of terminal jobs may be reused.
        """
        job_id = job_id or uuid.uuid4().hex[:12]
        
        # Opportunistically evict old terminal jobs so long-lived hosts
        # (gateways, bots, servers) don't retain every finished result.
        now = time.time()
        with self._lock:
            run_gc = now - self._last_gc > self._GC_INTERVAL
            if run_gc:
                self._last_gc = now
        if run_gc:
            self.cleanup_completed()
        
        job_info = JobInfo(
            job_id=job_id,
            status=JobStatus.PENDING,
            origin=dict(origin) if origin else {},
        )
        
        # Result handle owned by the manager (not the executor) so cancel_job
        # can wake get_result waiters even while ``func`` is still running.
        done: Future = Future()
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is not None and existing.status in (
                JobStatus.PENDING, JobStatus.RUNNING,
            ):
                raise ValueError(f"Job '{job_id}' is already active")
            # Publish job and future together so a concurrent cancel_job never
            # sees the new job paired with the old future.
            self._jobs[job_id] = job_info
            self._futures[job_id] = done
        # Persist the PENDING record before it starts so a crash between spawn
        # and first run still leaves a recoverable trace (reconciled as LOST).
        self._persist(job_info)
        
        def _fire_complete() -> None:
            _emit_job_completed(job_info)
            if on_complete is None:
                return
            info = job_info
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

        # The worker writes only to its own ``job_info`` (never re-looked-up by
        # id) so a later job reusing the id, or eviction, cannot be corrupted.
        job = job_info

        def _abort(error: BaseException, cancelled: bool = False) -> None:
            """Move a still-active job to a terminal state and resolve ``done``."""
            with self._lock:
                if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                    return
                job.status = JobStatus.CANCELLED if cancelled else JobStatus.FAILED
                job.completed_at = time.time()
                if not cancelled:
                    # Bare SystemExit()/KeyboardInterrupt() stringify to "".
                    job.error = str(error) or type(error).__name__
                if cancelled:
                    done.cancel()
                else:
                    done.set_exception(error)
            self._persist(job)
            # Failures must reach deliver-back/hook subscribers like any other
            # failure; cancellations stay silent, matching cancel_job().
            if not cancelled:
                _fire_complete()

        def _execute():
            with self._lock:
                if job.status == JobStatus.CANCELLED:  # cancelled while pending
                    return
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
            self._persist(job)

            try:
                result = func()
            except Exception as e:
                with self._lock:
                    if job.status == JobStatus.CANCELLED:
                        return
                    job.status = JobStatus.FAILED
                    job.completed_at = time.time()
                    job.error = str(e)
                self._persist(job)
                try:
                    _fire_complete()
                finally:
                    done.set_exception(e)
                return
            with self._lock:
                # Cancelled while running: discard the late outcome.
                if job.status == JobStatus.CANCELLED:
                    return
                job.status = JobStatus.COMPLETED
                job.completed_at = time.time()
                job.result = result
            self._persist(job)
            try:
                _fire_complete()
            finally:
                # Resolve even if on_complete raised a BaseException.
                done.set_result(result)

        def _run_job():
            try:
                _execute()
            except BaseException as e:
                # ``func`` raised a non-Exception (e.g. SystemExit); never
                # strand get_result callers.
                _abort(e)
                raise

        try:
            executor_future = self._executor.submit(_run_job)
        except BaseException as e:
            # e.g. submit after shutdown(): fail the job so its id is reusable
            # and get_result raises instead of blocking forever.
            _abort(e)
            raise
        # A queued work item dropped by the executor never runs _run_job.
        executor_future.add_done_callback(
            lambda f: _abort(CancelledError(), cancelled=True) if f.cancelled() else None
        )

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
            CancelledError: If the job was cancelled
            Exception: If the job failed, the original exception is re-raised
                (``RuntimeError`` with the stored error once evicted from
                memory)
        """
        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            # Evicted from memory: answer terminal outcomes from the durable store
            job = self._store.get(job_id) if self._store else None
            if job is None or job.status not in self._EVICTABLE_STATES:
                raise KeyError(f"Job {job_id} not found")
            if job.status == JobStatus.COMPLETED:
                return job.result
            if job.status == JobStatus.CANCELLED:
                raise CancelledError(f"Job {job_id} was cancelled")
            raise RuntimeError(job.error or f"Job {job_id} {job.status.value}")
        
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            # Distinct from builtin TimeoutError on Python 3.10.
            raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Attempt to cancel a job.

        A pending job never runs. A running job is marked ``CANCELLED``
        immediately and its eventual result is discarded (no ``on_complete``
        delivery); Python threads cannot be killed, so the worker thread is
        only released once ``func`` returns.
        
        Args:
            job_id: The job ID to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        with self._lock:
            job = self._jobs.get(job_id)
            future = self._futures.get(job_id)
            if future is None or job is None or job.status not in (
                JobStatus.PENDING, JobStatus.RUNNING,
            ):
                return False
            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()
            # Wakes any get_result waiter with CancelledError right away.
            future.cancel()
        self._persist(job)
        return True

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
          ``JOB_COMPLETED`` fires once with ``status="lost"``.
        - A job that is ``COMPLETED`` or ``LOST`` with an ``origin`` but was
          never ``delivered`` has ``redeliver`` invoked with its
          :class:`JobInfo`, so the origin gets the result or an "interrupted"
          notice. On a successful redeliver the job is marked ``delivered`` and
          persisted so it is not delivered twice on the next restart.

        Every persisted job is also re-hydrated into this manager's in-memory
        map so it remains queryable by id after the restart.

        No-op (returns zero counts) when no store is configured. Safe to call
        again (jobs live in this process are skipped), mirroring
        ``OutboundQueue.drain`` wiring.

        Args:
            redeliver: Callable invoked with a COMPLETED- or LOST-but-undelivered
                :class:`JobInfo` (check ``status``) to replay its deliver-back
                or announce the interruption. Best-effort — an
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
            # A repeat call (e.g. the gateway's boot pass after the lazy one in
            # get_job_manager) must not touch jobs started by this process.
            with self._lock:
                live = self._jobs.get(job.job_id)
            if live is not None and live.status in (
                JobStatus.PENDING, JobStatus.RUNNING,
            ):
                continue
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
                if job.error is None:
                    job.error = "Interrupted by a process restart"
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
                # LOST is persisted before the emit, so a crash loop observes
                # each orphan exactly once.
                _emit_job_completed(job)

            # A COMPLETED result or a LOST notice still owed to the origin.
            if (
                job.status in (JobStatus.COMPLETED, JobStatus.LOST)
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
                        "Re-delivered undelivered %s job %s to origin",
                        job.status.value, job.job_id,
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

    # Minimum seconds between opportunistic cleanups triggered by start_job
    _GC_INTERVAL = 60.0

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

        # Prune the durable store with the same age policy so it stays bounded.
        prune = getattr(self._store, "delete_older_than", None)
        if prune is not None:
            try:
                prune(now - max_age)
            except Exception as e:  # noqa: BLE001 — pruning is best-effort
                logger.debug("Pruning background job store failed (non-fatal): %s", e)
        
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


def _build_default_store() -> Optional[BackgroundJobStore]:
    """Best-effort construct the durable SQLite store for the global manager.

    Persists to ``<runs_dir>/background_jobs.db`` alongside the run ledger so
    ``/tasks`` and background subagents survive a restart. Any failure (missing
    data dir, read-only filesystem, sqlite error) is swallowed and the manager
    falls back to pure in-memory behaviour — durability is an enhancement, never
    a hard requirement. Set ``PRAISONAI_BACKGROUND_JOB_STORE=0`` to opt out.
    """
    import os

    if os.environ.get("PRAISONAI_BACKGROUND_JOB_STORE", "1") in ("0", "false", "False"):
        return None
    try:
        from .sqlite_store import SqliteBackgroundJobStore

        return SqliteBackgroundJobStore()
    except Exception as e:  # noqa: BLE001 — store is optional, never crash startup
        logger.debug("Durable background job store unavailable (non-fatal): %s", e)
        return None


def get_job_manager() -> BackgroundJobManager:
    """Get the global job manager instance.

    On first construction a durable :class:`BackgroundJobStore` is attached when
    one can be built (see :func:`_build_default_store`) and
    :meth:`BackgroundJobManager.reconcile_on_start` is run once so jobs orphaned
    by a prior crash are reconciled to ``LOST`` rather than silently lost.
    """
    global _global_job_manager
    with _global_lock:
        if _global_job_manager is None:
            store = _build_default_store()
            _global_job_manager = BackgroundJobManager(store=store)
            if store is not None:
                try:
                    _global_job_manager.reconcile_on_start()
                except Exception as e:  # noqa: BLE001 — never crash on startup recovery
                    logger.debug(
                        "Background job reconciliation on start failed "
                        "(non-fatal): %s", e,
                    )
        return _global_job_manager
