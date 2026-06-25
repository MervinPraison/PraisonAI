"""
Async bridge module - single source of truth for running coroutines synchronously.

This module provides a safe way to run async functions from sync contexts,
handling nested event loop scenarios without creating a new event loop
on every call (which is expensive and breaks multi-agent workflows).
"""
import asyncio
import os
import threading
import concurrent.futures
from concurrent.futures import CancelledError as FutureCancelledError, Future
from typing import Awaitable, TypeVar

T = TypeVar("T")

_DEFAULT_TIMEOUT = float(os.environ.get("PRAISONAI_RUN_SYNC_TIMEOUT", "300"))

class AsyncBridge:
    """Per-instance async runner. The module-level `run_sync()` keeps the
    historical shared default; embedders/services should construct their own."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _spawn_locked(self) -> asyncio.AbstractEventLoop:
        """Create the loop+thread; caller must hold ``self._lock``.

        The thread is marked ``daemon=True`` so that short-lived scripts
        (e.g. CLI commands, smoke tests) exit cleanly without waiting on
        the background loop to be shut down explicitly. Long-running
        server processes should call :meth:`shutdown` explicitly to cancel
        in-flight tasks before process exit.
        """
        # Enforce the "caller must hold the lock" contract. A non-reentrant
        # ``Lock`` that is currently held cannot be acquired again (even by the
        # owning thread), so a successful non-blocking acquire here proves the
        # lock was *not* held by the caller.
        if self._lock.acquire(blocking=False):
            self._lock.release()
            raise AssertionError(
                "_spawn_locked() must be called while holding self._lock"
            )
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

    def submit(self, coro):
        """Atomically (re)spawn loop if needed and submit coro. Returns concurrent.futures.Future."""
        with self._lock:
            loop = self._spawn_locked()
            return asyncio.run_coroutine_threadsafe(coro, loop)

    def run_sync(self, coro: Awaitable[T], *, timeout: float | None = _DEFAULT_TIMEOUT) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "run_sync() cannot be called from a running event loop"
            )
        fut = self.submit(coro)
        try:
            return fut.result(timeout=timeout)
        except (TimeoutError, concurrent.futures.TimeoutError):
            fut.cancel()
            try:
                fut.exception(timeout=1.0)
            except (
                TimeoutError,
                concurrent.futures.TimeoutError,
                asyncio.CancelledError,
                FutureCancelledError,
            ):
                pass
            raise
        except BaseException:
            fut.cancel()
            raise

    def shutdown(self, timeout: float = 5.0) -> None:
        # Snapshot loop and thread outside lock to avoid holding lock during wait
        with self._lock:
            loop, thread = self._loop, self._thread
            if loop is None:
                return
            # Clear references immediately to prevent new submissions
            self._loop = None
            self._thread = None
        
        # Now do the actual shutdown without holding the lock
        async def _cancel_all() -> None:
            self_task = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks(loop) 
                     if not t.done() and t is not self_task]
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

# Backwards-compatible module-level shared default.
#
# The shared bridge's lifecycle is owned exclusively by the process (via the
# ``atexit`` hook registered on first use). It is intentionally NOT exposed as a
# public ``shutdown()`` on the module surface: in a multi-agent / multi-tenant
# process every ``run_sync()`` caller shares this single loop+thread, so allowing
# any one caller to tear it down would silently cancel in-flight work belonging
# to every other agent/session. Embedders that need explicit lifecycle control
# must construct and own their own :class:`AsyncBridge` instance and pass it via
# dependency injection.
import atexit

# Single stable shared instance. It is created eagerly (cheap: no loop/thread is
# spawned until the first ``run_sync()`` call) so the reference never has to be
# rebound. Keeping the *same* object means callers that captured ``_BG`` always
# observe its live state, and only the process-exit hook tears it down.
_BG: AsyncBridge = AsyncBridge()


def _default_bridge() -> AsyncBridge:
    return _BG


def _shutdown_default() -> None:
    """Private process-exit hook: tear down the shared default bridge.

    Registered with :mod:`atexit`. This is the ONLY sanctioned way the shared
    default is shut down; it is deliberately absent from the public module
    surface so a single caller cannot terminate async work for the whole
    process. Embedders needing explicit lifecycle control own their own
    :class:`AsyncBridge` instance.
    """
    _BG.shutdown()


atexit.register(_shutdown_default)


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
    return _default_bridge().run_sync(coro, timeout=timeout)
