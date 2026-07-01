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

    A genuine async entry point is detected purely via
    ``inspect.iscoroutinefunction`` which is true for real ``async def``
    methods and for ``unittest.mock.AsyncMock``. ``astart`` is never called
    speculatively to probe its return value, which would otherwise run the
    agent's side effects twice, mask real errors, and re-materialise a dynamic
    ``astart`` child on an unspecced ``Mock``.
    """

    # ---------------------------------------------------------------
    # Prefer a genuine async entry point.
    #
    # Only ``inspect.iscoroutinefunction`` is used here: it is True for real
    # ``async def astart`` methods and for ``AsyncMock``, while a synchronous
    # ``Mock`` (or a dynamically materialised child mock) is correctly rejected
    # and routed to the synchronous fallback below.
    # ---------------------------------------------------------------
    astart = getattr(agent, "astart", None)

    if inspect.iscoroutinefunction(astart):
        return await astart(task)

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