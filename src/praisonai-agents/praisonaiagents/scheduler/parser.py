"""
Schedule expression parser for PraisonAI Agents.

Parses human-friendly schedule strings into ``Schedule`` objects.
No external dependencies for interval parsing; ``croniter`` is optional
and only imported when a cron expression is used.

Supported formats:
    "hourly"                  → every 3600s
    "daily"                   → every 86400s
    "*/30m"                   → every 1800s
    "*/6h"                    → every 21600s
    "*/10s"                   → every 10s
    "3600"                    → every 3600s (raw seconds)
    "cron:0 7 * * *"          → cron expression
    "at:2026-03-01T09:00:00"  → one-shot ISO timestamp
    "in 20 minutes"           → one-shot ~20min from now
"""

import re
from datetime import datetime, timedelta, timezone

from .models import Schedule

_KEYWORD_MAP = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}

_INTERVAL_RE = re.compile(
    r"^\*?/?\*?(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours)$",
    re.IGNORECASE,
)

_RELATIVE_RE = re.compile(
    r"^in\s+(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours)$",
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
}


def parse_schedule(expr: str) -> Schedule:
    """Parse a schedule expression string into a ``Schedule`` object.

    Raises ``ValueError`` for unrecognised expressions.
    """
    if not expr or not expr.strip():
        raise ValueError("Schedule expression cannot be empty")

    expr = expr.strip()

    # Keyword shortcuts
    lower = expr.lower()
    if lower in _KEYWORD_MAP:
        return Schedule(kind="every", every_seconds=_KEYWORD_MAP[lower])

    # Cron prefix
    if lower.startswith("cron:"):
        cron_expr = expr[5:].strip()
        if not cron_expr:
            raise ValueError("Empty cron expression after 'cron:' prefix")
        return Schedule(kind="cron", cron_expr=cron_expr)

    # At prefix (ISO timestamp)
    if lower.startswith("at:"):
        at_str = expr[3:].strip()
        if not at_str:
            raise ValueError("Empty timestamp after 'at:' prefix")
        return Schedule(kind="at", at=at_str)

    # Interval pattern: */30m, */6h, */10s
    m = _INTERVAL_RE.match(expr)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        seconds = value * _UNIT_MULTIPLIER[unit]
        return Schedule(kind="every", every_seconds=seconds)

    # Relative pattern: "in 20 minutes"
    m = _RELATIVE_RE.match(expr)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        delta_seconds = value * _UNIT_MULTIPLIER[unit]
        target = datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)
        return Schedule(kind="at", at=target.isoformat())

    # Raw numeric seconds
    try:
        seconds = int(expr)
        if seconds > 0:
            return Schedule(kind="every", every_seconds=seconds)
    except ValueError:
        pass

    raise ValueError(
        f"Unrecognised schedule expression: {expr!r}. "
        "Use 'hourly', 'daily', '*/30m', 'cron:EXPR', 'at:ISO', or 'in N minutes'."
    )
