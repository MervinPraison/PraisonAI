"""Shared scaffolding for ``ManagedBackendProtocol`` implementations.

``AnthropicManagedAgent`` (managed_agents.py) and ``LocalManagedAgent``
(managed_local.py) implement the same protocol contract and historically
re-implemented the same ``stream()`` producer/queue/sentinel scaffolding twice.
That duplication meant the async-safety fix for ``loop.run_in_executor`` and any
future protocol change had to be edited — and kept in sync — in two places.

``ManagedBackendBase`` owns that single copy of the queue pump. Concrete
backends implement only what actually differs:

    - ``_ensure_session()``            -> return a session id (already present on
      both concrete backends).
    - ``_iter_events(session_id, prompt)`` -> a *synchronous* iterator of text
      chunks. Runs on the producer thread, so blocking SDK calls are fine here.
    - ``_after_stream(full)`` [optional] -> post-stream bookkeeping (e.g. the
      local backend persists the assembled assistant turn + usage). Default is a
      no-op.

A third managed backend then implements two methods rather than copying the
whole streaming loop.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import AsyncIterator, Iterator, Optional

logger = logging.getLogger(__name__)


class ManagedBackendBase:
    """Mixin providing the shared ``stream()`` queue pump.

    Subclasses supply the session provider and the (synchronous) event source;
    this class turns them into an async generator without each backend shipping
    its own copy of the producer-thread + sentinel-queue plumbing.
    """

    def _ensure_session(self) -> str:  # pragma: no cover - implemented by subclass
        raise NotImplementedError

    def _iter_events(self, session_id: str, prompt: str) -> Iterator[str]:  # pragma: no cover
        """Yield text chunks for ``prompt`` on ``session_id`` (runs on a thread)."""
        raise NotImplementedError

    def _after_stream(self, full: str) -> None:
        """Hook for post-stream bookkeeping. Default: no-op."""

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Yield text chunks as the managed agent produces them.

        The synchronous ``_iter_events`` producer runs on a daemon thread and
        feeds a sentinel-terminated queue; the event loop is never blocked.
        """
        loop = asyncio.get_running_loop()
        q: "queue.Queue[Optional[str]]" = queue.Queue()

        def _producer() -> None:
            full = ""
            try:
                session_id = self._ensure_session()
                for chunk in self._iter_events(session_id, prompt):
                    if chunk:
                        text = str(chunk)
                        q.put(text)
                        full += text
            except Exception as e:  # noqa: BLE001 - surface, don't crash the loop
                logger.error("[managed] stream error: %s", e)
            finally:
                try:
                    self._after_stream(full)
                except Exception as e:  # noqa: BLE001
                    logger.error("[managed] post-stream hook error: %s", e)
                q.put(None)  # sentinel

        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()

        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            yield chunk
