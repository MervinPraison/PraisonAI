"""Canonical agent dispatch logic for schedulers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def adispatch_agent(agent: Any, task: str) -> Any:
    """Dispatch a task to an agent.

    Dispatch priority:

    1. Use ``agent.astart(task)`` if it exists and is an async callable.
    2. Otherwise use ``agent.start(task)`` in a worker thread.
    3. Raise ``AttributeError`` if neither entry point exists.

    This implementation intentionally avoids relying on ``hasattr()`` because
    ``unittest.mock.Mock`` dynamically reports arbitrary attributes as existing,
    which can incorrectly make a synchronous mock appear to implement
    ``astart()``.
    """

    # ---------------------------------------------------------------
    # Prefer a genuine async entry point.
    # ---------------------------------------------------------------
    astart = getattr(agent, "astart", None)

    if callable(astart):
        # Bound async methods
        if inspect.iscoroutinefunction(astart):
            return await astart(task)

        # Objects assigned directly that already return a coroutine
        try:
            result = astart(task)
        except TypeError:
            # Ignore incompatible signatures and continue to sync fallback.
            pass
        else:
            if inspect.isawaitable(result):
                return await result

    # ---------------------------------------------------------------
    # Fall back to synchronous execution.
    # ---------------------------------------------------------------
    start = getattr(agent, "start", None)

    if callable(start):
        return await asyncio.to_thread(start, task)

    raise AttributeError(
        f"{type(agent).__name__} must expose either an async 'astart(task)' "
        "or a sync 'start(task)' method."
    )