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
    "at 9am"                  → one-shot next 09:00
    "every day at 9am"        → daily at 09:00 (cron)
    "weekdays at 9am"         → Mon-Fri at 09:00 (cron)
    "every monday 9am"        → day-of-week at clock time (cron)
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

# Day-of-week names → cron day field (0 or 7 = Sunday). Aliases map to ranges.
_NL_DOW = {
    "sunday": "0", "sun": "0",
    "monday": "1", "mon": "1",
    "tuesday": "2", "tue": "2", "tues": "2",
    "wednesday": "3", "wed": "3",
    "thursday": "4", "thu": "4", "thur": "4", "thurs": "4",
    "friday": "5", "fri": "5",
    "saturday": "6", "sat": "6",
    "weekday": "1-5", "weekdays": "1-5",
    "weekend": "0,6", "weekends": "0,6",
}

# Clock time, e.g. "9am", "9:30pm", "17:00", "9 am".
_CLOCK_RE = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
    re.IGNORECASE,
)


def _parse_clock(text: str):
    """Parse a clock-time fragment into ``(hour, minute)`` or ``None``."""
    m = _CLOCK_RE.fullmatch(text.strip())
    if not m:
        return None
    hour = int(m.group("hour"))
    minute = int(m.group("minute") or 0)
    ampm = (m.group("ampm") or "").lower()
    if ampm:
        if hour < 1 or hour > 12:
            return None
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _natural_to_cron(expr: str):
    """Convert a natural-language schedule to a 5-field cron string.

    Returns the cron string for recurring day-of-week / daily clock times,
    or ``None`` when the expression is not a recurring NL form (callers then
    fall through to the one-shot / interval / cron paths).
    """
    lower = expr.lower().strip()
    lower = re.sub(r"^every\s+", "", lower)
    lower = re.sub(r"(?:^|\s)(?:at|on)\s+", " ", lower)
    lower = re.sub(r"\s+", " ", lower).strip()
    if not lower:
        return None

    # Drop filler words that carry no scheduling meaning once "every"/"at"/"on"
    # have been stripped ("every day at 9am" -> daily; "each morning" unsupported).
    _FILLER = {"day", "daily", "the", "of", "a"}
    tokens = [t for t in lower.split(" ") if t and t not in _FILLER]
    dow_parts = []
    clock = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # A comma-joined list of day names, e.g. "mon,wed,fri".
        if "," in tok and all(d in _NL_DOW for d in tok.split(",") if d):
            for d in tok.split(","):
                if d:
                    dow_parts.append(_NL_DOW[d])
            i += 1
            continue
        if tok in _NL_DOW:
            dow_parts.append(_NL_DOW[tok])
            i += 1
            continue
        # Otherwise attempt a clock time, possibly split across two tokens
        # ("9 am", "9:30 pm").
        joined = tok
        if i + 1 < len(tokens) and tokens[i + 1] in ("am", "pm"):
            joined = tok + tokens[i + 1]
            i += 1
        parsed = _parse_clock(joined)
        if parsed is None:
            return None
        if clock is not None:
            return None
        clock = parsed
        i += 1

    if clock is None:
        return None
    hour, minute = clock
    dow = ",".join(dow_parts) if dow_parts else "*"
    return f"{minute} {hour} * * {dow}"


def _clock_to_next_at(hour: int, minute: int, tz: str | None) -> str:
    """Return the next ISO timestamp for the given clock time (one-shot).

    The clock time denotes local time in the schedule's timezone (``tz`` or
    the process default), so ``at 9am`` fires at 09:00 in that zone rather
    than 09:00 UTC. Falls back to UTC when the timezone cannot be resolved.
    """
    try:
        from .due import resolve_schedule_timezone
        tzinfo = resolve_schedule_timezone(tz)
    except Exception:
        tzinfo = timezone.utc
    now = datetime.now(tzinfo)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.isoformat()


def parse_schedule(expr: str, tz: str | None = None) -> Schedule:
    """Parse a schedule expression string into a ``Schedule`` object.

    Raises ``ValueError`` for unrecognised expressions.
    """
    if not expr or not expr.strip():
        raise ValueError("Schedule expression cannot be empty")

    expr = expr.strip()
    if tz:
        from .due import resolve_schedule_timezone
        resolve_schedule_timezone(tz)

    # Keyword shortcuts
    lower = expr.lower()
    if lower in _KEYWORD_MAP:
        return Schedule(kind="every", every_seconds=_KEYWORD_MAP[lower], tz=tz)

    # Cron prefix
    if lower.startswith("cron:"):
        cron_expr = expr[5:].strip()
        if not cron_expr:
            raise ValueError("Empty cron expression after 'cron:' prefix")
        return Schedule(kind="cron", cron_expr=cron_expr, tz=tz)

    # At prefix (ISO timestamp)
    if lower.startswith("at:"):
        at_str = expr[3:].strip()
        if not at_str:
            raise ValueError("Empty timestamp after 'at:' prefix")
        return Schedule(kind="at", at=at_str, tz=tz)

    # Interval pattern: */30m, */6h, */10s
    m = _INTERVAL_RE.match(expr)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        seconds = value * _UNIT_MULTIPLIER[unit]
        return Schedule(kind="every", every_seconds=seconds, tz=tz)

    # Relative pattern: "in 20 minutes"
    m = _RELATIVE_RE.match(expr)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        delta_seconds = value * _UNIT_MULTIPLIER[unit]
        target = datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)
        return Schedule(kind="at", at=target.isoformat(), tz=tz)

    # Raw numeric seconds
    try:
        seconds = int(expr)
        if seconds > 0:
            return Schedule(kind="every", every_seconds=seconds, tz=tz)
    except ValueError:
        pass

    # Natural-language clock-time / day-of-week expressions:
    #   "at 9am"            → one-shot next 09:00
    #   "every day at 9am"  → daily at 09:00 (cron)
    #   "weekdays at 9am"   → Mon-Fri at 09:00 (cron)
    #   "every monday 9am"  → day-of-week at clock time (cron)
    # A bare clock time with no day / "every" is treated as a one-shot; any
    # recurring form ("every ...", "daily ...", a day-of-week) maps to cron.
    cron_expr = _natural_to_cron(expr)
    if cron_expr is not None:
        has_dow = cron_expr.rsplit(" ", 1)[-1] != "*"
        recurring = has_dow or bool(re.match(r"(?i)^\s*(every|daily|each)\b", expr))
        if recurring:
            return Schedule(kind="cron", cron_expr=cron_expr, tz=tz)
        minute, hour = cron_expr.split(" ")[:2]
        at = _clock_to_next_at(int(hour), int(minute), tz)
        return Schedule(kind="at", at=at, tz=tz)

    raise ValueError(
        f"Unrecognised schedule expression: {expr!r}. "
        "Use 'hourly', 'daily', '*/30m', 'cron:EXPR', 'at:ISO', 'in N minutes', "
        "'at 9am', 'every day at 9am', 'weekdays at 9am', or 'every monday 9am'."
    )
