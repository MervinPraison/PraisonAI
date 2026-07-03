"""
Schedule runner for PraisonAI Agents.

Checks the store for due jobs and returns them. Execution of the job
payload is the caller's responsibility (keeping the runner lightweight).
"""

import logging
from praisonaiagents._logging import get_logger
import time
from typing import List, Optional

from .models import ScheduleJob
from .protocols import ScheduleStoreProtocol
from .due import is_due as _is_due_shared

logger = get_logger(__name__)

class ScheduleRunner:
    """Stateless helper that inspects a store and returns due jobs.

    The runner does NOT own a loop or thread — callers decide how
    and when to call ``get_due_jobs()``.
    """

    def __init__(self, store: ScheduleStoreProtocol):
        self._store = store

    # ── public ───────────────────────────────────────────────────────

    def get_due_jobs(self) -> List[ScheduleJob]:
        """Return all enabled jobs that are due for execution *now*.

        Non-atomic: two tickers polling the same store may each see the same
        job as due. For at-most-once semantics across processes/hosts use
        :meth:`claim_due_jobs` when the store supports it.
        """
        now = time.time()
        due: List[ScheduleJob] = []
        for job in self._store.list():
            if not job.enabled:
                continue
            if self._is_due(job, now):
                due.append(job)
        return due

    def supports_atomic_claim(self) -> bool:
        """Whether the backing store offers an atomic cross-process claim."""
        return callable(getattr(self._store, "claim_due", None))

    def claim_due_jobs(
        self,
        owner_id: str,
        lease_seconds: float = 300.0,
    ) -> List[ScheduleJob]:
        """Atomically claim due jobs so each fires at most once across tickers.

        When the store implements ``claim_due`` this reserves each due job
        (advancing its schedule and taking a short lease) under a cross-process
        lock and returns only the jobs *this* caller won; competitors get an
        empty list and skip silently. When the store does not support atomic
        claims this falls back to :meth:`get_due_jobs` (non-atomic).

        Args:
            owner_id: Stable identifier for this ticker (process/host).
            lease_seconds: Lease window; a claim not completed expires after
                this so a crashed run is eventually retried.
        """
        claim = getattr(self._store, "claim_due", None)
        if callable(claim):
            return claim(time.time(), owner_id, lease_seconds)
        return self.get_due_jobs()

    def complete_run(self, job_id: str, owner_id: str) -> None:
        """Release a claimed job's lease after its run finishes (best-effort)."""
        complete = getattr(self._store, "complete", None)
        if callable(complete):
            complete(job_id, owner_id)

    def mark_run(
        self,
        job: ScheduleJob,
        status: str = "succeeded",
        result: Optional[str] = None,
        error: Optional[str] = None,
        duration: float = 0.0,
        delivered: bool = False,
    ) -> None:
        """Update ``last_run_at``, log history, and optionally delete one-shot jobs.

        Args:
            job: The job that was executed.
            status: Execution status (``"succeeded"``, ``"failed"``, ``"skipped"``).
            result: Agent response text.
            error: Error message if status is ``"failed"``.
            duration: Wall-clock seconds for execution.
            delivered: Whether result was delivered to a channel bot.
        """
        job.last_run_at = time.time()

        # Log execution history if the store supports it
        if hasattr(self._store, "log_run"):
            self._store.log_run(
                job_id=job.id,
                status=status,
                result=result,
                error=error,
                duration=duration,
                delivered=delivered,
                job_name=job.name,
            )

        if job.delete_after_run:
            self._store.remove(job.id)
        else:
            self._store.update(job)

    # ── internals ────────────────────────────────────────────────────

    def _is_due(self, job: ScheduleJob, now: float) -> bool:
        return _is_due_shared(job, now)
