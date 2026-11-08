"""
Inbound message debounce for PraisonAI bots.

Coalesces rapid messages from the same user into a single
agent.chat() call, preventing duplicate processing and wasted tokens.

Usage::

    debouncer = InboundDebouncer(debounce_ms=1500)
    coalesced = await debouncer.debounce("user123", "hello")
    # If user sends "world" within 1500ms, both are joined:
    # coalesced == "hello\\nworld"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from .._lockmap import LockMap

logger = logging.getLogger(__name__)


class InboundDebouncer:
    """Per-user message debouncer.

    Buffers rapid messages from the same user and flushes them as a
    single joined string after ``debounce_ms`` of silence, or once
    ``max_wait_ms`` has elapsed since the first buffered message
    (whichever comes first), so a steady stream still dispatches.

    Args:
        debounce_ms: Debounce window in milliseconds.  0 = disabled
            (immediate pass-through).
        separator: String used to join coalesced messages.
        max_wait_ms: Hard cap on how long a buffer may stay open.
            ``None`` = 5x ``debounce_ms``; 0 = unbounded (legacy).
        max_buffered: Flush immediately once this many messages are
            buffered.  0 = no cap.
    """

    def __init__(
        self,
        debounce_ms: int = 0,
        separator: str = "\n",
        max_wait_ms: Optional[int] = None,
        max_buffered: int = 100,
    ) -> None:
        self._debounce_s = max(0, debounce_ms) / 1000.0
        if max_wait_ms is None:
            max_wait_ms = 5 * max(0, debounce_ms)
        self._max_wait_s = max(0, max_wait_ms) / 1000.0
        self._max_buffered = max(0, max_buffered)
        self._first_enqueued: Dict[str, float] = {}
        self._separator = separator
        self._buffers: Dict[str, List[str]] = {}
        self._timers: Dict[str, asyncio.TimerHandle] = {}
        self._futures: Dict[str, List[asyncio.Future]] = {}
        self._locks = LockMap()

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        return self._locks.get(user_id)

    async def debounce(self, user_id: str, text: str) -> str:
        """Buffer *text* for *user_id* and return coalesced result.

        If ``debounce_ms == 0``, returns *text* immediately (no buffering).

        Otherwise, waits for the debounce window to expire, then returns
        all buffered messages joined by ``separator``.

        Returns:
            The (possibly coalesced) message text.
        """
        if self._debounce_s <= 0:
            return text

        lock = self._get_lock(user_id)
        async with lock:
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()

            # Add to buffer
            if user_id not in self._buffers:
                self._buffers[user_id] = []
                self._futures[user_id] = []

            self._buffers[user_id].append(text)
            self._futures[user_id].append(future)

            # Cancel existing timer and reschedule, bounded by max-wait
            if user_id in self._timers:
                self._timers[user_id].cancel()

            now = loop.time()
            first = self._first_enqueued.setdefault(user_id, now)
            if self._max_buffered and len(self._buffers[user_id]) >= self._max_buffered:
                self._flush(user_id)
            else:
                delay = self._debounce_s
                if self._max_wait_s > 0:
                    delay = max(0.0, min(delay, first + self._max_wait_s - now))
                self._timers[user_id] = loop.call_later(
                    delay,
                    self._flush,
                    user_id,
                )

        # Wait for flush (outside lock so other messages can enqueue)
        return await future

    def _flush(self, user_id: str) -> None:
        """Flush the buffer for *user_id*, resolving all pending futures."""
        messages = self._buffers.pop(user_id, [])
        futures = self._futures.pop(user_id, [])
        self._timers.pop(user_id, None)
        self._first_enqueued.pop(user_id, None)

        if not messages:
            return

        coalesced = self._separator.join(messages)
        for fut in futures:
            if not fut.done():
                fut.set_result(coalesced)

    @property
    def pending_count(self) -> int:
        """Number of users with buffered messages."""
        return len(self._buffers)

    def cancel_all(self) -> int:
        """Cancel all pending debounce timers.  Returns count cancelled."""
        count = 0
        for user_id in list(self._timers.keys()):
            handle = self._timers.pop(user_id, None)
            if handle:
                handle.cancel()
                count += 1
            # Resolve futures with whatever is buffered
            self._flush(user_id)
        return count
