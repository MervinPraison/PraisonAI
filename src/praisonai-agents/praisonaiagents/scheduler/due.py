"""
Shared due-check logic for scheduled jobs.

Extracted so both the stateless :class:`~praisonaiagents.scheduler.runner.ScheduleRunner`
and any store implementing atomic ``claim_due`` (e.g.
:class:`~praisonaiagents.scheduler.store.FileScheduleStore`) share one
definition of "is this job due now?" rather than duplicating it.
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


def resolve_schedule_timezone(tz: str | None = None) -> ZoneInfo:
    """Resolve an explicit or instance-default IANA timezone.

    ``PRAISONAI_SCHEDULE_TIMEZONE`` supplies the process-wide default; UTC is
    retained when neither the schedule nor the instance selects a timezone.
    """
    name = tz or os.environ.get("PRAISONAI_SCHEDULE_TIMEZONE") or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(f"Unknown IANA timezone: {name!r}") from exc


def next_fire_time(
    cron_expr: str,
    base: float,
    tz: str | None = None,
) -> float:
    """Return the next cron fire time (epoch) strictly after ``base``.

    Pure helper owning the "compute next fire from a base" step so wrapper
    tickers can share core's cron timing rather than re-implementing it.
    Requires the optional ``croniter`` engine; callers guard its import and
    the ``(ValueError, KeyError, TypeError)`` raised by malformed expressions.
    """
    from croniter import croniter  # type: ignore[import-untyped]

    base_datetime = datetime.fromtimestamp(base, resolve_schedule_timezone(tz))
    return croniter(cron_expr, base_datetime).get_next(datetime).timestamp()


def is_due(
    job: Any,
    now: float,
    default_timezone: str | None = None,
) -> bool:
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
                # A naive ``at`` reflects the user's wall clock (they typed it
                # from local time), so interpret it in the schedule's timezone:
                # the explicit tz / PRAISONAI_SCHEDULE_TIMEZONE when set,
                # otherwise the local zone rather than UTC — a naive string in a
                # non-UTC zone would otherwise fire an hour (or more) off.
                tz = sched.tz or default_timezone
                if tz or os.environ.get("PRAISONAI_SCHEDULE_TIMEZONE"):
                    tzinfo = resolve_schedule_timezone(tz)
                else:
                    tzinfo = datetime.now().astimezone().tzinfo
                target = target.replace(tzinfo=tzinfo)
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
            next_run = next_fire_time(
                sched.cron_expr,
                base_time,
                sched.tz or default_timezone,
            )
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
