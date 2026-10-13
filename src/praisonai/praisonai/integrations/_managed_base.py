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
import functools
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

    def interrupt(self) -> None:
        """Stop the in-flight run. Default: no-op."""

    def _interrupt_in_background(self) -> None:
        """Call ``interrupt()`` on a daemon thread so the event loop never blocks."""
        def _run() -> None:
            try:
                self.interrupt()
            except Exception:  # noqa: BLE001
                logger.debug("[managed] interrupt failed", exc_info=True)

        threading.Thread(target=_run, daemon=True).start()

    async def _execute_in_executor(self, sync_fn, prompt: str, **kwargs) -> str:
        """Run ``sync_fn(prompt, stream_live=...)`` off-loop, honouring ``timeout``.

        On timeout the backend is interrupted (best-effort) before re-raising;
        the worker thread itself cannot be killed.
        """
        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(
            None,
            functools.partial(
                sync_fn, prompt, stream_live=bool(kwargs.get("stream_live", False)),
            ),
        )
        timeout = kwargs.get("timeout")
        if timeout is None:
            return await fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._interrupt_in_background()
            raise

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Yield text chunks as the managed agent produces them.

        The synchronous ``_iter_events`` producer runs on a daemon thread and
        feeds a sentinel-terminated queue; the event loop is never blocked.

        To stop early, close the generator (``await gen.aclose()`` or
        ``contextlib.aclosing``); a bare ``break`` only closes it once the
        generator is garbage-collected.
        """
        loop = asyncio.get_running_loop()
        q: "queue.Queue[Optional[str]]" = queue.Queue()
        stop = threading.Event()  # set when the consumer stops reading

        def _producer() -> None:
            full = ""
            try:
                session_id = self._ensure_session()
                if stop.is_set():
                    return  # consumer left during session setup; never start the run
                for chunk in self._iter_events(session_id, prompt):
                    if stop.is_set():
                        # The consumer-side interrupt may have fired before this
                        # run existed, so interrupt again now that it does.
                        try:
                            self.interrupt()
                        except Exception:  # noqa: BLE001
                            logger.debug("[managed] interrupt failed", exc_info=True)
                        break
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

        try:
            while True:
                chunk = await loop.run_in_executor(None, q.get)
                if chunk is None:
                    break
                yield chunk
        finally:
            # Runs on aclose() / cancellation (or GC after a bare break).
            stop.set()
            if thread.is_alive():
                # The producer may be blocked waiting on upstream events (e.g. a
                # long tool call), so interrupt independently of it.
                self._interrupt_in_background()
