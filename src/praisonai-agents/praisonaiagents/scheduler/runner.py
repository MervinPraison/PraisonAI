"""
Schedule runner for PraisonAI Agents.

Checks the store for due jobs and returns them. Execution of the job
payload is the caller's responsibility (keeping the runner lightweight).
"""

from praisonaiagents._logging import get_logger
import time
from typing import List, Optional, Tuple

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

    # ── job-to-job context chaining ───────────────────────────────────

    def resolve_context(self, job: ScheduleJob) -> Tuple[str, List[str]]:
        """Resolve a job's upstream context from its ``context_from`` refs.

        For each declared upstream (id or name) this reads the most-recent
        *successful* output from the store's execution history and formats it as
        clearly-delimited, bounded context ready to prepend to the job's
        ``message`` — the job→job data-flow that turns isolated jobs into a
        composable pipeline (fetch → analyse → deliver).

        Pure and side-effect-free: the caller (a wrapper executor) decides how
        to inject the returned text and how to honour ``on_missing_context``.

        Args:
            job: The downstream job whose upstream context to resolve.

        Returns:
            A ``(context, missing)`` tuple where ``context`` is the joined,
            delimited upstream text (``""`` when nothing resolved) and
            ``missing`` lists the refs that had no resolvable successful output
            (so the caller can apply the ``on_missing_context`` policy).
        """
        refs = job.context_from or []
        if not refs:
            return "", []
        # Clamp the budget to a non-negative bound so a misconfigured
        # zero/negative value enforces "no injected body" rather than silently
        # returning the full upstream output (which would break the bounded
        # contract). Truncation is always applied.
        budget = max(job.context_max_chars, 0)
        parts: List[str] = []
        missing: List[str] = []
        for ref in refs:
            output = self._last_successful_output(ref)
            if not output:
                missing.append(ref)
                continue
            output = output[:budget]
            parts.append(f"### Context from '{ref}'\n{output}")
        return "\n\n".join(parts), missing

    def _last_successful_output(self, ref: str) -> Optional[str]:
        """Return the most-recent successful result for an upstream job ref.

        ``ref`` may be a job id or a human-readable name. Resolution reuses the
        store's existing execution history (``get_history``) so no new
        persistence surface is required — the last output is already recorded
        there per run.
        """
        get_history = getattr(self._store, "get_history", None)
        if not callable(get_history):
            return None
        job_id = ref
        get = getattr(self._store, "get", None)
        if not (callable(get) and get(ref) is not None):
            get_by_name = getattr(self._store, "get_by_name", None)
            if callable(get_by_name):
                match = get_by_name(ref)
                if match is not None:
                    job_id = match.id
        try:
            records = get_history(job_id=job_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Failed to read history for upstream %r: %s", ref, e)
            return None
        for record in records or []:
            if getattr(record, "status", None) == "succeeded" and getattr(record, "result", None):
                return record.result
        return None

    # ── internals ────────────────────────────────────────────────────

    def _is_due(self, job: ScheduleJob, now: float) -> bool:
        return _is_due_shared(job, now)
