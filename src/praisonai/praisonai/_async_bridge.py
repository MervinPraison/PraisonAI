"""
Async bridge module - single source of truth for running coroutines synchronously.

This module provides a safe way to run async functions from sync contexts,
handling nested event loop scenarios without creating a new event loop
on every call (which is expensive and breaks multi-agent workflows).
"""
import asyncio
import atexit
import os
import threading
from concurrent.futures import Future
from typing import Awaitable, TypeVar

T = TypeVar("T")

_DEFAULT_TIMEOUT = float(os.environ.get("PRAISONAI_RUN_SYNC_TIMEOUT", "300"))

class _BackgroundLoop:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def get(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                # non-daemon so shutdown must be explicit and clean
                self._thread = threading.Thread(
                    target=self._loop.run_forever,
                    name="praisonai-async",
                    daemon=False,
                )
                self._thread.start()
            return self._loop

    def shutdown(self, timeout: float = 5.0) -> None:
        with self._lock:
            loop, thread = self._loop, self._thread
            if loop is None:
                return
            # Cancel outstanding tasks, then stop the loop.
            async def _cancel_all() -> None:
                tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                asyncio.run_coroutine_threadsafe(_cancel_all(), loop).result(timeout)
            finally:
                loop.call_soon_threadsafe(loop.stop)
                if thread is not None:
                    thread.join(timeout)
                if not loop.is_closed():
                    loop.close()
                self._loop = None
                self._thread = None

_BG = _BackgroundLoop()
atexit.register(_BG.shutdown)


def run_sync(coro: Awaitable[T], *, timeout: float | None = _DEFAULT_TIMEOUT) -> T:
    """
    Run a coroutine synchronously, safe inside a running loop.
    
    This function automatically detects if there's already a running event loop
    and handles the execution appropriately:
    - If no loop is running: uses background loop (consistent behavior)
    - If a loop is running: schedules on background loop (safe path)
    
    Args:
        coro: The coroutine to run
        timeout: Maximum time to wait for completion (seconds)
        
    Returns:
        The result of the coroutine
        
    Raises:
        TimeoutError: If timeout is exceeded
        Any exception raised by the coroutine
    """
    try:
        asyncio.get_running_loop()
        running = True
    except RuntimeError:
        running = False

    if not running:
        # Reuse the background loop instead of creating a new one per call.
        fut: Future = asyncio.run_coroutine_threadsafe(coro, _BG.get())
        return fut.result(timeout=timeout)

    fut = asyncio.run_coroutine_threadsafe(coro, _BG.get())
    return fut.result(timeout=timeout)


def shutdown() -> None:
    """Public hook for servers (gateway, a2u, mcp_server) to stop the bridge cleanly."""
    _BG.shutdown()