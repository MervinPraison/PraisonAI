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


def localize_wall_clock(target: datetime, tz: str | None = None) -> datetime:
    """Attach the zone a naive wall-clock timestamp was written in.

    A naive ``at`` string is what a person typed from their own clock, so it
    means *that wall-clock time in the schedule's zone*, resolved in order:
    the schedule's explicit ``tz``, then ``PRAISONAI_SCHEDULE_TIMEZONE``, then
    the system's local zone. It is never UTC by default -- stamping UTC is
    exactly the defect that made one-shot jobs fire an hour off outside UTC.

    An already-aware ``target`` is returned unchanged: an explicit offset in
    the string always wins over any default.

    The local-zone branch uses :meth:`datetime.astimezone` on the naive value
    so the offset is the one in force *on that date* (DST-correct), not the
    offset in force right now.

    Raises ``ValueError`` when the named zone is not a known IANA zone.
    """
    if target.tzinfo is not None:
        return target
    name = tz or os.environ.get("PRAISONAI_SCHEDULE_TIMEZONE")
    if name:
        return target.replace(tzinfo=resolve_schedule_timezone(name))
    return target.astimezone()


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


def scheduled_instant(
    job: Any,
    now: float,
    default_timezone: str | None = None,
) -> float | None:
    """Return the epoch of the occurrence this due job is firing *for*.

    When a recurring job becomes due at ``now`` it is firing for a specific
    scheduled slot that may lie in the past (the process was down when the
    slot arrived). This returns that slot's canonical instant so a misfire
    policy can decide whether recovery is still within an acceptable grace
    window. ``None`` is returned when there is no meaningful past slot (a
    never-run interval job, or a kind/expression that cannot be evaluated).

    - ``every``: the *first* slot that came due after ``last_run_at``
      (``last_run_at + every_seconds``). Its age measures how long the job has
      been overdue — the meaningful lateness for a coalesced recovery.
    - ``cron``: the last cron fire at or before ``now`` (the slot being
      recovered for a daily/weekly schedule).
    - ``at``: the target instant itself.
    """
    sched = job.schedule
    if sched.kind == "every":
        if sched.every_seconds is None or job.last_run_at is None:
            return None
        if now - job.last_run_at < sched.every_seconds:
            return None
        return job.last_run_at + sched.every_seconds
    if sched.kind == "at":
        if sched.at is None:
            return None
        try:
            return localize_wall_clock(
                datetime.fromisoformat(sched.at),
                sched.tz or default_timezone,
            ).timestamp()
        except (ValueError, TypeError):
            return None
    if sched.kind == "cron":
        if sched.cron_expr is None:
            return None
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            return None
        try:
            base_datetime = datetime.fromtimestamp(
                now, resolve_schedule_timezone(sched.tz or default_timezone)
            )
            return croniter(sched.cron_expr, base_datetime).get_prev(datetime).timestamp()
        except (ValueError, KeyError, TypeError):
            return None
    return None


def is_misfire(
    job: Any,
    now: float,
    default_timezone: str | None = None,
) -> bool:
    """Whether a *due* job's occurrence should be suppressed as a misfire.

    Shared by every atomic-claim store so the misfire decision is defined once.
    Returns ``True`` when the occurrence the job is firing for is older than
    ``misfire_grace_seconds`` — a stale run whose slot passed while the process
    was down. Such an occurrence is recorded as ``missed`` (observable) instead
    of firing a late, no-longer-useful run. An occurrence still within the
    grace window (or a first run) coalesces into a single normal fire on
    recovery, the pre-existing behaviour.

    With no grace set this is always ``False`` — existing jobs keep firing
    exactly as before. A first run (``last_run_at is None``) is never a misfire
    for any kind: there is no missed *recurrence* to suppress, only the initial
    fire, which must always run (matching ``is_due``'s never-run branches).
    """
    grace = getattr(job, "misfire_grace_seconds", None)
    if grace is None:
        return False
    # A first run is the initial fire, not a recovered recurrence — always let
    # it run. ``every`` already encodes this (``scheduled_instant`` returns
    # ``None`` with no ``last_run_at``); make it explicit for ``cron``/``at``
    # too so a never-run job past a stale slot is not marked missed unfired.
    if getattr(job, "last_run_at", None) is None:
        return False
    # Tolerate a mis-typed grace (e.g. a hand-edited quoted YAML value that
    # slipped past coercion): a bad policy value must never raise and abort the
    # whole claim pass — treat it as "no misfire" so other due jobs still fire.
    try:
        grace_val = float(grace)
    except (TypeError, ValueError):
        return False
    instant = scheduled_instant(job, now, default_timezone)
    if instant is None:
        return False
    age = now - instant
    if age <= 0:
        return False
    return age > grace_val


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

    A bounded recurring job carries an optional stop condition — a ``max_runs``
    budget and/or an ``until`` end instant. Once either is met the job is no
    longer due, so it never fires or delivers again before the claim path
    retires it (see :meth:`ScheduleJob.should_retire`).
    """
    sched = job.schedule

    # Bounded-run stop conditions short-circuit before any kind check so a
    # spent job is neither due nor delivered (no final stale send).
    max_runs = getattr(job, "max_runs", None)
    run_count = getattr(job, "run_count", 0)
    if max_runs is not None and run_count >= max_runs:
        return False
    until = getattr(job, "until", None)
    if until is not None:
        try:
            until_ts = localize_wall_clock(
                datetime.fromisoformat(until),
                sched.tz or default_timezone,
            ).timestamp()
        except (ValueError, TypeError):
            # Fail safe: a stop bound that cannot be parsed must NOT let the
            # job run past it forever. Treat the job as not-due; the claim path
            # then retires it via ``ScheduleJob.should_retire`` (which returns
            # True for an unparseable ``until``) rather than firing it.
            logger.warning("Invalid 'until' timestamp for job %s: %s", job.id, until)
            return False
        if now >= until_ts:
            return False

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
            # ``parse_schedule`` stamps every ``at`` it produces with its zone,
            # so a string reaching here is normally aware and evaluated as-is.
            # A naive string (a job stored before zones were stamped, or a
            # hand-written config.yaml entry) is a legacy wall-clock value:
            # ``localize_wall_clock`` reads it in the schedule tz, else the
            # instance default, else PRAISONAI_SCHEDULE_TIMEZONE, else the
            # runner's local zone -- never UTC by default.
            target = localize_wall_clock(
                datetime.fromisoformat(sched.at),
                sched.tz or default_timezone,
            )
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
