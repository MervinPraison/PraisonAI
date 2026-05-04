"""Shared primitives for sync & async schedulers."""

class ScheduleParser:
    """Parse schedule expressions into intervals in seconds."""
    
    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.
        
        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/6h" -> 21600 seconds (every 6 hours)
        - "*/30s" -> 30 seconds (every 30 seconds)
        - "3600" -> 3600 seconds (plain number)
        
        Args:
            schedule_expr: Schedule expression string
            
        Returns:
            Interval in seconds
            
        Raises:
            ValueError: If schedule format is not supported
            
        Examples:
            >>> ScheduleParser.parse("hourly")
            3600
            >>> ScheduleParser.parse("*/30m")
            1800
            >>> ScheduleParser.parse("daily")
            86400
        """
        expr = schedule_expr.strip().lower()
        
        if expr == "daily":
            return 86400
        if expr == "hourly":
            return 3600
        if expr.isdigit():
            return int(expr)
        if expr.startswith("*/"):
            part = expr[2:]
            if part.endswith("m"):
                return int(part[:-1]) * 60
            if part.endswith("h"):
                return int(part[:-1]) * 3600
            if part.endswith("s"):
                return int(part[:-1])
            return int(part)
        raise ValueError(f"Unsupported schedule format: {schedule_expr}")


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
    called from sync code, runs it to completion via asyncio.run.
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
                # No running loop, use asyncio.run
                try:
                    asyncio.run(result)
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