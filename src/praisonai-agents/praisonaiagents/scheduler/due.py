"""
Shared due-check logic for scheduled jobs.

Extracted so both the stateless :class:`~praisonaiagents.scheduler.runner.ScheduleRunner`
and any store implementing atomic ``claim_due`` (e.g.
:class:`~praisonaiagents.scheduler.store.FileScheduleStore`) share one
definition of "is this job due now?" rather than duplicating it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


def is_due(job: Any, now: float) -> bool:
    """Return ``True`` if ``job`` is due to run at epoch ``now``.

    Supports the three schedule kinds: ``every`` (interval), ``at`` (one-shot
    ISO timestamp) and ``cron`` (5-field expression, requires optional
    ``croniter``). Disabled jobs are the caller's concern and are not filtered
    here.
    """
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
            # Evaluate against the caller-supplied ``now`` (not wall-clock) so
            # one-shot jobs are deterministic and consistent with every/cron.
            return now >= target.timestamp()
        except (ValueError, TypeError):
            logger.warning("Invalid 'at' timestamp for job %s: %s", job.id, sched.at)
            return False

    if sched.kind == "cron":
        if sched.cron_expr is None:
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
        try:
            cron = croniter(sched.cron_expr, base_time)
            next_run = cron.get_next(float)
        except (ValueError, KeyError, TypeError) as e:
            # A malformed cron expression must not abort the whole tick loop
            # (which iterates all jobs) — treat this job as not-due instead.
            logger.warning(
                "Invalid cron expression for job %s (%r): %s",
                job.id, sched.cron_expr, e,
            )
            return False
        return now >= next_run

    return False
