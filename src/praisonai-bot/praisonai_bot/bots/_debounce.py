"""
Inbound message debounce for PraisonAI bots.

Coalesces rapid messages from the same user into a single
agent.chat() call, preventing duplicate processing and wasted tokens.

Usage::

    debouncer = InboundDebouncer(debounce_ms=1500)
    batch = await debouncer.debounce("user123", "hello")
    # If user sends "world" within 1500ms, the final caller of the burst gets
    # one batch (batch.final == "hello\\nworld"); superseded callers get
    # ``None`` and short-circuit instead of running the agent again.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .._lockmap import LockMap

logger = logging.getLogger(__name__)

# Plain-text control words exempt from inbound debouncing (mirror of the core
# attribution in ``praisonaiagents.bots.admission``).
_DEBOUNCE_CONTROL_WORDS = frozenset({"stop", "cancel", "status"})


def _fallback_should_debounce_inbound(
    text: str, *, has_media: bool = False, allow_debounce: bool = True
) -> bool:
    """Dependency-free mirror of the core debounce eligibility gate.

    Bound to ``should_debounce_inbound`` only when the installed core predates
    the shared predicate. A parity test pins it to the core function so the two
    cannot drift while both exist; every install that has the core keeps
    answering through the shared predicate, which stays the single authority.
    """
    if not allow_debounce or has_media:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return not (
        stripped.startswith("/") or stripped.lower() in _DEBOUNCE_CONTROL_WORDS
    )


try:  # Shared eligibility gate (Issue #6717); optional at import time.
    from praisonaiagents.bots.admission import should_debounce_inbound
except Exception:  # pragma: no cover - only when core predates the shared gate
    # The bot's dependency floor (``praisonaiagents>=1.7.6``) admits core
    # releases that predate this symbol, and the dist flywheel ships the bot
    # and the core as separate wheels. Without this fallback the module-level
    # imports in telegram/discord/slack — and the gateway handler — raise
    # ImportError, so the bot cannot start at all on such an install. The
    # fallback keeps the eligibility rule instead of losing it; new cores keep
    # answering through the shared predicate, so the rule has one authority.
    should_debounce_inbound = _fallback_should_debounce_inbound  # type: ignore

# A buffer flushes after this many debounce windows, even if messages keep arriving.
_MAX_WAIT_FACTOR = 5
# A buffer flushes as soon as it holds this many messages.
_MAX_BUFFERED = 100


@dataclass
class DebouncedBatch:
    """One dispatchable turn coalesced from a debounce burst.

    ``final`` is the separator-joined burst text to hand the agent (the same
    input the debouncer always produced). ``preceding`` lists the burst's
    earlier messages in arrival order, for callers that want the parts.
    """

    final: str
    preceding: List[str] = field(default_factory=list)


class InboundDebouncer:
    """Per-user message debouncer.

    Buffers rapid messages from the same user and flushes them as a
    single joined string after ``debounce_ms`` of silence.  A buffer is
    also flushed ``_MAX_WAIT_FACTOR`` x ``debounce_ms`` after its first
    message, or as soon as it holds ``_MAX_BUFFERED`` messages, so a steady
    stream still dispatches.

    Args:
        debounce_ms: Debounce window in milliseconds.  0 = disabled
            (immediate pass-through).
        separator: String used to join coalesced messages.
    """

    def __init__(
        self,
        debounce_ms: int = 0,
        separator: str = "\n",
    ) -> None:
        self._debounce_s = max(0, debounce_ms) / 1000.0
        self._max_wait_s = _MAX_WAIT_FACTOR * self._debounce_s
        self._max_buffered = _MAX_BUFFERED
        self._first_enqueued: Dict[str, float] = {}
        self._separator = separator
        self._buffers: Dict[str, List[str]] = {}
        self._timers: Dict[str, asyncio.TimerHandle] = {}
        self._futures: Dict[str, List[asyncio.Future]] = {}
        self._locks = LockMap()

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        return self._locks.get(user_id)

    async def debounce(self, user_id: str, text: str) -> Optional[DebouncedBatch]:
        """Buffer *text* for *user_id* and return the burst's single batch.

        If ``debounce_ms == 0``, returns a one-message batch immediately
        (no buffering).

        Otherwise, waits for the debounce window to expire. The final
        caller of the burst receives :class:`DebouncedBatch` with the
        separator-joined text and dispatches the one agent turn;
        superseded callers (their text folded into the batch) receive
        ``None`` so their adapters short-circuit instead of re-running
        the agent with the same coalesced string.
        """
        if self._debounce_s <= 0:
            return DebouncedBatch(final=text)

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
        """Flush the buffer for *user_id*, resolving all pending futures.

        Only the final pending caller is resolved with the coalesced
        batch — one agent turn per burst; superseded callers are resolved
        with ``None`` (see :meth:`debounce`).
        """
        messages = self._buffers.pop(user_id, [])
        futures = self._futures.pop(user_id, [])
        self._timers.pop(user_id, None)
        self._first_enqueued.pop(user_id, None)

        if not messages:
            return

        batch = DebouncedBatch(
            final=self._separator.join(messages), preceding=messages[:-1]
        )
        # The last *unfinished* caller owns the batch: a cancelled caller's
        # future is already done, and resolving by position would then hand
        # ``None`` to every survivor and drop the burst on the floor.
        unfinished = [fut for fut in futures if not fut.done()]
        if unfinished:
            for fut in unfinished[:-1]:
                fut.set_result(None)
            unfinished[-1].set_result(batch)

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
