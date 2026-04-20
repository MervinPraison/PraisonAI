"""Shared primitives for sync & async schedulers."""

class ScheduleParser:
    """Shared schedule expression parser for both sync and async schedulers."""
    
    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.
        
        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/1h" -> 3600 seconds (every 1 hour)
        - "60" -> 60 seconds (plain number)
        
        Args:
            schedule_expr: Schedule expression string
            
        Returns:
            Interval in seconds
            
        Raises:
            ValueError: If schedule format is not supported
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


def backoff_delay(attempt: int, *, base: float = 2.0, cap: float = 60.0) -> float:
    """Exponential backoff, capped. Used by both sync & async schedulers."""
    return min(base ** attempt, cap)


def safe_call(cb, *args) -> None:
    """Run a user callback without letting it tear the scheduler down."""
    if cb is None:
        return
    try:
        cb(*args)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Scheduler callback raised: %s", e)