"""Shared primitives for sync & async schedulers."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Emit the "croniter missing" guidance at most once per process so a cron
# schedule that degrades to a coarse interval is visible without log spam.
_CRON_WARNING_EMITTED = False


def _warn_cron_unavailable() -> None:
    """Warn once that cron degrades to a coarse interval without ``croniter``.

    Mirrors core ``praisonaiagents.scheduler.due.is_due``: a ``cron:`` schedule
    needs the optional ``croniter`` engine to honour wall-clock timing. Without
    it the wrapper falls back to a process-relative interval (the pre-#3526
    behaviour), so surface a one-time actionable warning instead of degrading
    silently.
    """
    global _CRON_WARNING_EMITTED
    if not _CRON_WARNING_EMITTED:
        _CRON_WARNING_EMITTED = True
        logger.warning(
            "croniter not installed — cron schedules fall back to a "
            "process-relative interval and will not honour wall-clock timing "
            "or catch up missed slots. Install with: pip install croniter"
        )


class ScheduleTicker:
    """Wall-clock aware "when does this schedule fire next?" helper.

    Unlike :class:`ScheduleParser` (which collapses everything to a fixed
    integer interval anchored to process start), the ticker honours the real
    schedule kind:

    - ``cron:M H * * *`` fires at the actual wall-clock time-of-day via core
      ``croniter`` (the same engine the gateway already uses), so a restart
      does **not** re-phase the schedule and a slot missed while the process
      was down/dormant runs **exactly once** on resume before re-anchoring to
      the next future occurrence.
    - Plain interval expressions (``hourly``, ``*/30m``, raw seconds) keep the
      previous fixed-interval behaviour, so nothing regresses.

    The ticker owns only the *timing*; the caller keeps its executor/delivery
    wiring. State is a single ``last_run_at`` epoch persisted by the caller,
    mirroring core ``ScheduleJob.last_run_at``.
    """

    def __init__(self, schedule_expr: str, last_run_at: Optional[float] = None):
        self.schedule_expr = schedule_expr.strip()
        self.last_run_at: Optional[float] = last_run_at
        # Anchor for a never-run cron job, mirroring core ``ScheduleJob``'s use
        # of ``created_at``: the schedule is measured from here so a slot that
        # falls between this anchor and "now" is treated as missed → caught up.
        self.created_at: float = time.time()
        self._is_cron = self.schedule_expr.lower().startswith("cron:")
        # For plain intervals we reuse the existing integer-interval parse so
        # behaviour is byte-for-byte identical to the fixed-interval loop.
        self._interval: Optional[int] = None
        if not self._is_cron:
            self._interval = ScheduleParser.parse(self.schedule_expr)

    @property
    def is_cron(self) -> bool:
        """Whether this schedule is a wall-clock cron expression."""
        return self._is_cron

    def _cron_expr(self) -> str:
        return self.schedule_expr[len("cron:"):].strip()

    def is_due(self, now: Optional[float] = None) -> bool:
        """Return ``True`` if a cron slot is due (used for downtime catch-up).

        For interval schedules this always returns ``True`` on first tick
        (there is no wall-clock slot to have missed).
        """
        if not self._is_cron:
            return True
        if now is None:
            now = time.time()
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            _warn_cron_unavailable()
            return False
        # Measure from the last run, or from creation for a never-run job
        # (mirrors core ``is_due`` using ``last_run_at or created_at``).
        base = self.last_run_at if self.last_run_at is not None else self.created_at
        try:
            next_run = croniter(self._cron_expr(), base).get_next(float)
        except (ValueError, KeyError, TypeError):
            return False
        return now >= next_run

    def seconds_until_next(self, now: Optional[float] = None) -> float:
        """Seconds to sleep before the next execution.

        - cron: seconds until the next wall-clock occurrence after ``now``
          (clamped to ``>= 0``); if ``croniter`` is unavailable, falls back to
          the best-effort interval so scheduling still progresses.
        - interval: the fixed interval seconds.
        """
        if not self._is_cron:
            return float(self._interval or 0)
        if now is None:
            now = time.time()
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            # Degrade gracefully to the coarse interval rather than busy-loop,
            # but surface a one-time warning so the degrade isn't silent.
            _warn_cron_unavailable()
            return float(ScheduleParser._parse_cron_to_interval(self._cron_expr()))
        try:
            next_run = croniter(self._cron_expr(), now).get_next(float)
        except (ValueError, KeyError, TypeError):
            return float(ScheduleParser._parse_cron_to_interval(self._cron_expr()))
        return max(0.0, next_run - now)

    def mark_ran(self, now: Optional[float] = None) -> None:
        """Advance persisted ``last_run_at`` after a run (at-most-once anchor)."""
        self.last_run_at = time.time() if now is None else now


class ScheduleParser:
    """Shared schedule expression parser for both sync and async schedulers."""

    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.

        The shared grammar (keywords, ``*/N{m,h,s}``, raw seconds) is owned by
        core ``praisonaiagents.scheduler.parser.parse_schedule``; this wrapper
        delegates to it and derives an integer interval for the polling loop.
        The ``cron:`` → best-effort interval collapse is wrapper-specific and
        stays local, since the interval loop needs an integer rather than a
        natively-run cron schedule.

        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "weekly" -> 604800 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/1h" -> 3600 seconds (every 1 hour)
        - "60" -> 60 seconds (plain number)
        - "cron:M H * * *" -> best-effort interval from cron expression

        Args:
            schedule_expr: Schedule expression string

        Returns:
            Interval in seconds

        Raises:
            ValueError: If schedule format is not supported
        """
        expr = schedule_expr.strip()

        # Wrapper-specific: cron → best-effort integer interval for polling loop.
        if expr.lower().startswith("cron:"):
            return ScheduleParser._parse_cron_to_interval(expr[5:].strip())

        # Wrapper-specific backward-compat: bare ``*/N`` (no unit) means N
        # seconds. Core ``parse_schedule`` requires a unit suffix, so handle
        # the unit-less case here to avoid rejecting previously-valid configs.
        if expr.startswith("*/"):
            part = expr[2:].strip()
            if part.isdigit():
                return int(part)

        # Delegate the shared grammar to the single core owner.
        from praisonaiagents.scheduler.parser import parse_schedule

        try:
            sched = parse_schedule(expr)
        except ValueError:
            raise ValueError(f"Unsupported schedule format: {schedule_expr}")
        if sched.kind == "every" and sched.every_seconds is not None:
            return sched.every_seconds
        raise ValueError(f"Unsupported schedule format: {schedule_expr}")

    @staticmethod
    def _parse_cron_to_interval(cron_expr: str) -> int:
        """Convert a cron expression to a best-effort interval in seconds.

        Handles common cron patterns generated by the blueprint system:
        - ``"M H * * DOW"`` → 86400 (daily) if hour is fixed
        - ``"*/N * * * *"`` → N × 60 (every N minutes)
        - ``"M * * * *"`` → 3600 (hourly) if minute is fixed
        - Everything else → 60 (check every minute)
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            return 60  # malformed cron → poll frequently

        minute, hour = parts[0], parts[1]

        # Interval-based: "*/15 * * * *" → every 15 minutes
        if minute.startswith("*/") and hour == "*":
            try:
                return int(minute[2:]) * 60
            except ValueError:
                pass

        # Hourly: "30 * * * *" → run at minute 30 of every hour
        if minute.isdigit() and hour == "*":
            return 3600

        # Daily: "0 8 * * 1-5" or "0 8 * * *" → run at a specific hour daily
        if minute.isdigit() and hour.isdigit():
            return 86400

        # Fallback: poll every 60 seconds for complex patterns
        return 60


def backoff_delay(
    attempt: int,
    *,
    base: float = 2.0,
    initial: float = 30.0,
    cap: float = 300.0,
    jitter: float = 0.1,
) -> float:
    """Exponential backoff with jitter, capped. Used by both sync & async schedulers."""
    import random
    delay = min(max(initial, base ** attempt), cap)
    # Apply multiplicative jitter to avoid thundering herd
    return delay * random.uniform(1 - jitter, 1 + jitter)


def safe_call(cb, *args) -> None:
    """Run a user callback without letting it tear the scheduler down.

    Supports both sync and async callables. When called from a running event
    loop with a coroutine-returning callback, schedules it on the loop; when
    called from sync code, runs it via the shared persistent loop instead
    of creating + tearing down a fresh one per call.
    """
    if cb is None:
        return
    import logging
    import asyncio
    import inspect
    log = logging.getLogger(__name__)
    try:
        result = cb(*args)
        if inspect.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No loop here: dispatch to the shared persistent loop instead
                # of creating + tearing down a fresh one.
                try:
                    from .._async_bridge import run_sync
                    run_sync(result)
                except Exception as e:
                    log.error("Scheduler async callback raised: %s", e)
            else:
                # Running loop exists, schedule as task
                task = loop.create_task(result)
                task.add_done_callback(
                    lambda t: t.exception() and log.error(
                        "Scheduler async callback raised: %s", t.exception()
                    )
                )
    except Exception as e:
        log.error("Scheduler callback raised: %s", e)