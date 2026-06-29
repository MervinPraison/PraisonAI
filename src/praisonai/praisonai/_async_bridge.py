"""
Async bridge module - single source of truth for running coroutines synchronously.

This module provides a safe way to run async functions from sync contexts,
handling nested event loop scenarios without creating a new event loop
on every call (which is expensive and breaks multi-agent workflows).
"""
import asyncio
import atexit
import contextlib
import contextvars
import os
import threading
import concurrent.futures
from concurrent.futures import CancelledError as FutureCancelledError, Future
from typing import Awaitable, Iterator, Optional, TypeVar

T = TypeVar("T")

_DEFAULT_TIMEOUT = float(os.environ.get("PRAISONAI_RUN_SYNC_TIMEOUT", "300"))

class AsyncBridge:
    """Per-instance async runner. The module-level `run_sync()` keeps the
    historical shared default; embedders/services should construct their own."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Permanently-closed flag. Set by ``shutdown(permanent=True)`` for
        # scope-owned bridges so a leaked context (e.g. an ``asyncio.Task`` that
        # copied the ContextVar inside a ``scoped_bridge`` block) cannot silently
        # resurrect an orphaned loop+thread after the scope exits. The shared
        # default is never marked permanent so its only teardown is the atexit
        # hook at process exit.
        self._closed = False
        # Identity of the thread currently holding ``self._lock``. Set under the
        # lock by ``get()``/``submit()`` so ``_spawn_locked()`` can verify the
        # *caller* (not merely *someone*) owns the lock.
        self._lock_owner: int | None = None

    def _spawn_locked(self) -> asyncio.AbstractEventLoop:
        """Create the loop+thread; caller must hold ``self._lock``.

        The thread is marked ``daemon=True`` so that short-lived scripts
        (e.g. CLI commands, smoke tests) exit cleanly without waiting on
        the background loop to be shut down explicitly. Long-running
        server processes should call :meth:`shutdown` explicitly to cancel
        in-flight tasks before process exit.
        """
        # Enforce the "caller must hold the lock" contract. We compare the
        # recorded lock owner against the current thread so the check detects
        # both an unlocked lock *and* a lock held by a different thread (a bare
        # non-blocking acquire could only prove the lock was free for *anyone*).
        if self._lock_owner != threading.get_ident():
            raise AssertionError(
                "_spawn_locked() must be called while holding self._lock"
            )
        # Refuse to resurrect a permanently-closed (scope-owned) bridge. This
        # guards the case where a context copied inside ``scoped_bridge`` outlives
        # the ``with`` block and later tries to run work through the now-shut-down
        # bridge: instead of silently starting an orphaned loop+thread that no
        # scope or atexit hook owns, fail loudly.
        if self._closed:
            raise RuntimeError(
                "AsyncBridge has been shut down and cannot be reused; "
                "this usually means a context outlived its scoped_bridge() block"
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
            self._lock_owner = threading.get_ident()
            try:
                return self._spawn_locked()
            finally:
                self._lock_owner = None

    def submit(self, coro):
        """Atomically (re)spawn loop if needed and submit coro. Returns concurrent.futures.Future."""
        with self._lock:
            self._lock_owner = threading.get_ident()
            try:
                loop = self._spawn_locked()
                return asyncio.run_coroutine_threadsafe(coro, loop)
            finally:
                self._lock_owner = None

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

    def shutdown(self, timeout: float = 5.0, *, permanent: bool = False) -> None:
        """Tear down the loop+thread.

        Args:
            timeout: Seconds to wait for in-flight tasks to cancel and the
                background thread to join.
            permanent: When ``True`` the bridge is marked closed and may not be
                reused; a later ``run_sync``/``submit`` raises ``RuntimeError``
                rather than silently resurrecting an orphaned loop. Used by
                :func:`scoped_bridge` for the bridges it owns. The shared default
                is shut down with ``permanent=False`` so it never poisons callers.
        """
        # Snapshot loop and thread outside lock to avoid holding lock during wait
        with self._lock:
            if permanent:
                self._closed = True
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

# Single stable shared instance. It is created eagerly (cheap: no loop/thread is
# spawned until the first ``run_sync()`` call) so the reference never has to be
# rebound. Keeping the *same* object means callers that captured ``_BG`` always
# observe its live state, and only the process-exit hook tears it down.
_BG: AsyncBridge = AsyncBridge()


# Context-scoped override. When set (via :func:`scoped_bridge`), callers in that
# context — and any code they transitively invoke, including async tasks that
# copy the context — resolve to the scoped bridge instead of the shared default.
# This lets server/gateway/managed callers bind a per-session loop+thread
# without rewriting internal modules that import ``run_sync`` directly.
_bridge_var: contextvars.ContextVar[Optional[AsyncBridge]] = contextvars.ContextVar(
    "praisonai_async_bridge", default=None
)


def _default_bridge() -> AsyncBridge:
    """Resolve the active bridge: context-scoped override, else shared default."""
    scoped = _bridge_var.get()
    if scoped is not None:
        return scoped
    return _BG


def current_bridge() -> AsyncBridge:
    """Return the :class:`AsyncBridge` active in the current context.

    Returns the bridge bound by an enclosing :func:`scoped_bridge` block, or the
    process-wide shared default when no scope is active. Prefer this over reaching
    for the module-level ``_BG`` so embedders can override the bridge via
    dependency injection.
    """
    return _default_bridge()


@contextlib.contextmanager
def scoped_bridge(bridge: Optional[AsyncBridge] = None) -> Iterator[AsyncBridge]:
    """Bind a per-scope :class:`AsyncBridge` for the duration of the ``with`` block.

    Server callers (``praisonai serve``, gateway, managed agents) can isolate a
    session's sync→async work onto its own loop+thread so a stuck coroutine in one
    session does not park the shared default loop for every other session::

        with scoped_bridge() as bridge:
            run_sync(some_coro())   # uses ``bridge`` instead of the global default
            ...
        # bridge is shut down automatically on exit when created here.

    Args:
        bridge: An existing bridge to bind. When ``None`` a fresh bridge is created
            for the scope and shut down on exit. A caller-provided bridge is left
            untouched (the caller owns its lifecycle).
    """
    owns = bridge is None
    if bridge is None:
        bridge = AsyncBridge()
    token = _bridge_var.set(bridge)
    try:
        yield bridge
    finally:
        _bridge_var.reset(token)
        if owns:
            # ``permanent=True`` poisons the bridge so a context that copied the
            # ContextVar inside this block cannot resurrect it after we exit.
            bridge.shutdown(permanent=True)


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
