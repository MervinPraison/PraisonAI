"""Shared helpers for the package's aiui pages (component dicts, no I/O).

Pages return ``aiui.layout([...])``: the dashboard (and the app shell, which
hosts it) renders the declared components instead of a raw JSON block.

Untrusted text (errors, channel reasons, workflow input and output) only goes
into components the dashboard renders as text: ``table`` cells, ``badge``,
``caption``, ``text`` and ``empty``. ``alert``/``metric`` render through
innerHTML, so they only get fixed strings and numbers from this package.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

MAX_CELL = 120


def clip(value: Any, limit: int = MAX_CELL) -> str:
    """A one-line table cell: ``—`` for nothing, long text cut with an ellipsis."""
    if value is None or value == "":
        return "—"
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def count(value: Any) -> int:
    """An int for a metric; anything else (None, text, a list) becomes its size or 0."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, dict, set)):
        return len(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def duration(seconds: Any) -> str:
    """``3d 4h``, ``2h 5m``, ``4m 10s``, ``12s``; ``—`` when unknown."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "—"
    if total <= 0:
        return "—"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def timestamp(value: Any) -> str:
    """An epoch time as local ``YYYY-MM-DD HH:MM:SS``; other values as text."""
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return _dt.datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return "—"
    return clip(value, 32)
