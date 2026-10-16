"""
Burst coalescing for inbound gateway hooks (Issue #5867).

Applies the core ``CoalesceConfig`` contract: deliveries that share a group key
are buffered and dispatched as **one** run carrying the latest payload, once
the group has been quiet for ``window_seconds`` or ``max_wait_seconds`` after
its first delivery — whichever comes first.

Single event loop only (all calls happen on the gateway's loop), so no locks.
The number of pending groups is capped at ``max_groups`` so a burst across many
distinct entities cannot grow the buffer without bound; ``submit`` then returns
``None`` and the gateway answers with a retryable 503.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ``dispatch(hook, latest_payload, count)`` runs the coalesced turn.
Dispatch = Callable[[Any, Dict[str, Any], int], Awaitable[Any]]


class _Group:
    __slots__ = ("hook", "payload", "count", "first_at", "last_at", "task")

    def __init__(self, hook: Any, payload: Dict[str, Any], now: float) -> None:
        self.hook = hook
        self.payload = payload
        self.count = 1
        self.first_at = now
        self.last_at = now
        self.task: Optional[asyncio.Task] = None


class HookCoalescer:
    """Debounce buffer keyed by ``HookConfig.resolve_coalesce_key``."""

    def __init__(
        self,
        dispatch: Dispatch,
        clock: Callable[[], float] = time.monotonic,
        max_groups: int = 10_000,
    ) -> None:
        self._dispatch = dispatch
        self._clock = clock
        self._max_groups = max_groups
        self._groups: Dict[str, _Group] = {}
        # Every timer/dispatch task, including groups already removed from
        # ``_groups`` whose run is in progress, so shutdown can cancel them.
        self._tasks: Set[asyncio.Task] = set()

    def __len__(self) -> int:
        return len(self._groups)

    def submit(self, key: str, hook: Any, payload: Dict[str, Any]) -> Optional[int]:
        """Buffer a delivery; returns how many deliveries the group now holds.

        Returns ``None`` (nothing buffered) when a new group would exceed
        ``max_groups``.
        """
        now = self._clock()
        group = self._groups.get(key)
        if group is None:
            if len(self._groups) >= self._max_groups:
                return None
            group = _Group(hook, payload, now)
            self._groups[key] = group
            group.task = asyncio.ensure_future(self._fire_when_due(key, group))
            self._tasks.add(group.task)
            group.task.add_done_callback(self._tasks.discard)
        else:
            group.hook = hook
            group.payload = payload
            group.count += 1
            group.last_at = now
        return group.count

    async def _fire_when_due(self, key: str, group: _Group) -> None:
        cfg = group.hook.coalesce
        while True:
            remaining = cfg.deadline(group.first_at, group.last_at) - self._clock()
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)
        if self._groups.get(key) is group:
            del self._groups[key]
        try:
            await self._dispatch(group.hook, group.payload, group.count)
        except Exception as e:  # noqa: BLE001 - never kill the loop
            logger.error(
                "Coalesced hook '%s' run failed: %s",
                getattr(group.hook, "path", "?"), e,
            )

    async def aclose(self) -> None:
        """Cancel pending groups and in-progress runs (gateway shutdown)."""
        pending = len(self._groups)
        self._groups.clear()
        tasks = list(self._tasks)
        if tasks:
            logger.warning(
                "Cancelling %d coalesced hook task(s) on shutdown "
                "(%d still pending, %d running)",
                len(tasks), pending, len(tasks) - pending,
            )
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
