"""
Async bridge module - single source of truth for running coroutines synchronously.

This module provides a safe way to run async functions from sync contexts,
handling nested event loop scenarios without creating a new event loop
on every call (which is expensive and breaks multi-agent workflows).
"""
import asyncio
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

    def _spawn_locked(self) -> asyncio.AbstractEventLoop:
        """Create the loop+thread; caller must hold ``self._lock``.

        The thread is marked ``daemon=True`` so that short-lived scripts
        (e.g. CLI commands, smoke tests) exit cleanly without waiting on
        the background loop to be shut down explicitly. Long-running
        servers (gateway, a2u, mcp_server) should call :func:`shutdown`
        explicitly to cancel in-flight tasks before process exit.
        """
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name="praisonai-async",
                daemon=True,
            )
            self._thread.start()
        return self._loop

    def get(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            return self._spawn_locked()

    def get_unlocked(self) -> asyncio.AbstractEventLoop:
        """Get loop assuming caller holds _lock. For run_sync() use only."""
        return self._spawn_locked()

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


def run_sync(coro: Awaitable[T], *, timeout: float | None = _DEFAULT_TIMEOUT) -> T:
    """
    Run a coroutine synchronously using the background loop.
    
    IMPORTANT: This function cannot be called from within a running event loop
    as it would cause deadlock. Use 'await coro' directly from async contexts.
    
    Args:
        coro: The coroutine to run
        timeout: Maximum time to wait for completion (seconds)
        
    Returns:
        The result of the coroutine
        
    Raises:
        RuntimeError: If called from within a running event loop
        TimeoutError: If timeout is exceeded
        Any exception raised by the coroutine
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "run_sync() cannot be called from a running event loop; "
            "await the coroutine directly instead."
        )

    # Submit the coroutine inside the lock to prevent shutdown races
    with _BG._lock:
        loop = _BG.get_unlocked()
        fut: Future = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result(timeout=timeout)


def shutdown() -> None:
    """Public hook for servers (gateway, a2u, mcp_server) to stop the bridge cleanly."""
    _BG.shutdown()