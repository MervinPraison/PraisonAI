"""
Schedule runner for PraisonAI Agents.

Checks the store for due jobs and returns them. Execution of the job
payload is the caller's responsibility (keeping the runner lightweight).
"""

import logging
import time
from datetime import datetime, timezone
from typing import List

from .models import ScheduleJob
from .store import FileScheduleStore

logger = logging.getLogger(__name__)


class ScheduleRunner:
    """Stateless helper that inspects a store and returns due jobs.

    The runner does NOT own a loop or thread — callers decide how
    and when to call ``get_due_jobs()``.
    """

    def __init__(self, store: FileScheduleStore):
        self._store = store

    # ── public ───────────────────────────────────────────────────────

    def get_due_jobs(self) -> List[ScheduleJob]:
        """Return all enabled jobs that are due for execution *now*."""
        now = time.time()
        due: List[ScheduleJob] = []
        for job in self._store.list():
            if not job.enabled:
                continue
            if self._is_due(job, now):
                due.append(job)
        return due

    def mark_run(self, job: ScheduleJob) -> None:
        """Update ``last_run_at`` and optionally delete one-shot jobs."""
        job.last_run_at = time.time()
        if job.delete_after_run:
            self._store.remove(job.id)
        else:
            self._store.update(job)

    # ── internals ────────────────────────────────────────────────────

    def _is_due(self, job: ScheduleJob, now: float) -> bool:
        sched = job.schedule

        if sched.kind == "every":
            if sched.every_seconds is None:
                return False
            if job.last_run_at is None:
                return True  # Never run → due immediately
            return (now - job.last_run_at) >= sched.every_seconds

        if sched.kind == "at":
            if sched.at is None:
                return False
            if job.last_run_at is not None:
                return False  # Already ran
            try:
                target = datetime.fromisoformat(sched.at)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return datetime.now(timezone.utc) >= target
            except (ValueError, TypeError):
                logger.warning("Invalid 'at' timestamp for job %s: %s", job.id, sched.at)
                return False

        if sched.kind == "cron":
            return self._cron_is_due(job, now)

        return False

    @staticmethod
    def _cron_is_due(job: ScheduleJob, now: float) -> bool:
        """Check cron schedule. Requires optional ``croniter``."""
        if job.schedule.cron_expr is None:
            return False
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "croniter not installed — cron schedules are unavailable. "
                "Install with: pip install croniter"
            )
            return False

        base_time = job.last_run_at or job.created_at
        cron = croniter(job.schedule.cron_expr, base_time)
        next_run = cron.get_next(float)
        return now >= next_run
