"""
Async-safe concurrency primitives for agent state protection.

This module provides dual-lock abstractions that automatically select
the appropriate lock type based on the execution context (sync vs async).
"""
import asyncio
import copy
import threading
from typing import Any
from contextlib import contextmanager, asynccontextmanager
from weakref import WeakKeyDictionary


def run_async_in_sync_context(coro):
    """
    Run an async coroutine to completion from a sync context with proper
    event loop handling.

    Handles the common cases:
    1. No event loop exists - use asyncio.run()
    2. Event loop already running - avoid deadlock by running the coroutine
       to completion in a dedicated thread with its own event loop.

    This is a live production helper on the sync tool-calling path (see
    ``tool_execution.py``): it bridges ``async def`` tool bodies into the sync
    tool loop, otherwise a bare un-awaited coroutine would be handed to the
    model as the tool result and the tool body would never run (silent data
    loss).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No event loop - safe to use asyncio.run()
        return asyncio.run(coro)

    # Event loop exists - avoid deadlock by running in dedicated thread
    import concurrent.futures

    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result(timeout=300)  # 5 minute timeout


class DualLock:
    """
    A dual-lock abstraction that automatically selects threading.Lock or asyncio.Lock
    based on the execution context.
    
    This enables the same Agent to be safely used in both sync and async contexts
    without blocking the event loop.
    
    Example:
        ```python
        lock = DualLock()
        
        # In sync context
        with lock.sync():
            # Uses threading.Lock
            pass
            
        # In async context  
        async with lock.async_lock():
            # Uses asyncio.Lock
            pass
        ```
    """
    
    def __init__(self):
        """Initialize with a single underlying mutex shared by both call styles.

        A single ``threading.Lock`` backs both ``sync()`` and ``async_lock()``
        so that holding one genuinely blocks the other — mutual exclusion is
        real across sync and async callers of the same instance. A plain
        ``Lock`` (not ``RLock``) is used because the async path acquires on a
        worker thread but releases on the event-loop thread, which ``RLock``'s
        thread-ownership semantics forbid. Same-thread ``sync()`` reentrancy is
        preserved explicitly via an owner/depth guard below. The per-event-loop
        ``asyncio.Lock`` only serialises coroutines on the same loop so they
        queue for the underlying mutex cooperatively instead of every coroutine
        racing straight into the blocking acquire.
        """
        self._thread_lock = threading.Lock()  # Shared mutex (cross-thread release ok)
        self._owner_lock = threading.Lock()    # Guards the reentrancy bookkeeping
        self._owner_thread: Any = None         # Thread id currently holding for sync reentrancy
        self._owner_depth = 0
        self._async_locks = WeakKeyDictionary()  # Per-event-loop async gate

    def __deepcopy__(self, memo):
        """Return an unlocked primitive with no event-loop state sharing."""
        result = type(self)()
        memo[id(self)] = result
        return result
    
    @contextmanager
    def sync(self):
        """Acquire lock in synchronous context using the shared mutex.

        Re-entrant for the same thread: a nested ``sync()`` on the thread that
        already holds the mutex does not re-acquire (and cannot self-deadlock).
        """
        me = threading.get_ident()
        with self._owner_lock:
            reentrant = self._owner_thread == me and self._owner_depth > 0
            if reentrant:
                self._owner_depth += 1
        if not reentrant:
            self._thread_lock.acquire()
            with self._owner_lock:
                self._owner_thread = me
                self._owner_depth = 1
        try:
            yield
        finally:
            with self._owner_lock:
                self._owner_depth -= 1
                released = self._owner_depth == 0
                if released:
                    self._owner_thread = None
            if released:
                self._thread_lock.release()
            
    def _get_async_lock(self):
        """Get or create an asyncio.Lock for the current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("async_lock() must be called from an async context")
        
        if loop not in self._async_locks:
            self._async_locks[loop] = asyncio.Lock()
        return self._async_locks[loop]

    async def _acquire_shared_mutex(self, loop):
        """Acquire the shared mutex off-loop, releasing it if we are cancelled.

        ``run_in_executor`` can complete (mutex acquired) after the awaiting
        task is cancelled. If we let the ``CancelledError`` propagate without
        checking, the worker would strand the mutex forever. We therefore wait
        on the acquisition, and on cancellation ensure the mutex is released
        once the worker finishes so no caller waits indefinitely.
        """
        future = loop.run_in_executor(None, self._thread_lock.acquire)
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            # The worker may still be mid-acquire; wait for it to settle, then
            # release if it managed to take the mutex so it is never orphaned.
            try:
                acquired = await future
            except asyncio.CancelledError:
                acquired = False
            if acquired:
                self._thread_lock.release()
            raise

    @asynccontextmanager
    async def async_lock(self):
        """Acquire lock in asynchronous context using the shared mutex.

        Backs onto the *same* ``threading.Lock`` as ``sync()`` so a concurrent
        sync caller is genuinely excluded (and vice-versa). The blocking
        ``acquire`` is offloaded to a worker thread so the event loop is never
        blocked while waiting; the matching ``release`` (allowed cross-thread on
        a plain ``Lock``) happens on the loop thread. A per-event-loop
        ``asyncio.Lock`` serialises coroutines on this loop first so they don't
        all spin up executor hops at once.

        While the mutex is held, the *event-loop thread* is registered as the
        sync owner so a nested ``with lock.sync()`` on that thread (used by the
        async handoff seeding path) is treated as re-entrant instead of
        self-deadlocking against the mutex we already hold.
        """
        loop = asyncio.get_running_loop()
        async_gate = self._get_async_lock()
        async with async_gate:
            await self._acquire_shared_mutex(loop)
            me = threading.get_ident()
            with self._owner_lock:
                self._owner_thread = me
                self._owner_depth = 1
            try:
                yield
            finally:
                with self._owner_lock:
                    self._owner_depth -= 1
                    released = self._owner_depth == 0
                    if released:
                        self._owner_thread = None
                if released:
                    self._thread_lock.release()
            
    def is_async_context(self) -> bool:
        """Check if we're currently in an async context."""
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False


class AsyncSafeState:
    """
    A thread and async-safe state container that automatically
    chooses the appropriate locking mechanism based on context.
    
    Example:
        ```python
        state = AsyncSafeState(initial_value=[])
        
        # Sync usage
        with state.lock():
            state.value.append("item")
            
        # Async usage
        async with state.async_lock():
            state.value.append("item")
            
        # Legacy compatibility (direct context manager)
        with state:
            state.value.append("item")
        ```
    """
    
    def __init__(self, initial_value: Any = None):
        self.value = initial_value
        self._lock = DualLock()
        self._activity_lock = threading.Lock()
        self._async_holders = 0
        self._copying = False

    def __deepcopy__(self, memo):
        """Copy protected state, rejecting overlap with asynchronous access."""
        result = type(self).__new__(type(self))
        memo[id(self)] = result
        with self._activity_lock:
            if self._async_holders:
                raise RuntimeError(
                    "Cannot deepcopy AsyncSafeState during asynchronous access"
                )
            if self._copying:
                raise RuntimeError("AsyncSafeState deepcopy is already in progress")
            self._copying = True
        try:
            with self.lock():
                result.value = copy.deepcopy(self.value, memo)
        finally:
            with self._activity_lock:
                self._copying = False
        result._lock = DualLock()
        result._activity_lock = threading.Lock()
        result._async_holders = 0
        result._copying = False
        return result
        
    @contextmanager 
    def lock(self):
        """Acquire lock in sync context."""
        with self._lock.sync():
            yield self.value
            
    @asynccontextmanager
    async def async_lock(self):
        """Acquire lock in async context."""
        # Fail fast BEFORE blocking on the shared mutex: an in-progress
        # synchronous deepcopy holds the mutex for the whole copy, so waiting on
        # it here would block until the copy finished instead of surfacing the
        # documented RuntimeError (and could stall the loop indefinitely).
        self._raise_if_copying()
        async with self._lock.async_lock():
            self._begin_async_access()
            try:
                yield self.value
            finally:
                self._end_async_access()

    def _raise_if_copying(self) -> None:
        """Reject entry while a synchronous deepcopy of this state is active."""
        with self._activity_lock:
            if self._copying:
                raise RuntimeError(
                    "Cannot access AsyncSafeState during synchronous deepcopy"
                )

    def _begin_async_access(self) -> None:
        """Register async access unless a synchronous copy is in progress."""
        with self._activity_lock:
            if self._copying:
                raise RuntimeError(
                    "Cannot access AsyncSafeState during synchronous deepcopy"
                )
            self._async_holders += 1

    def _end_async_access(self) -> None:
        """Unregister one active asynchronous accessor."""
        with self._activity_lock:
            self._async_holders -= 1
            
    def __enter__(self):
        """Support for synchronous context manager protocol (backward compatibility)."""
        self._sync_guard = self._lock.sync()
        self._sync_guard.__enter__()
        return self.value
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support for synchronous context manager protocol (backward compatibility)."""
        return self._sync_guard.__exit__(exc_type, exc_val, exc_tb)
        
    async def __aenter__(self):
        """Support for asynchronous context manager protocol."""
        # Fail fast before blocking on the mutex an in-progress deepcopy holds.
        self._raise_if_copying()
        loop = asyncio.get_running_loop()
        async_lock = self._lock._get_async_lock()
        await async_lock.acquire()
        try:
            # Hold the SAME underlying mutex used by the sync path so async and
            # sync accessors are mutually exclusive (matches DualLock.async_lock).
            # Cancellation-safe acquire so the mutex is never stranded if the
            # awaiting task is cancelled mid-acquisition.
            await self._lock._acquire_shared_mutex(loop)
            try:
                self._begin_async_access()
            except Exception:
                self._lock._thread_lock.release()
                raise
        except Exception:
            async_lock.release()
            raise
        return self.value
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support for asynchronous context manager protocol."""
        async_lock = self._lock._get_async_lock()
        try:
            self._end_async_access()
        finally:
            try:
                self._lock._thread_lock.release()
            finally:
                async_lock.release()
        return None
            
    def get(self) -> Any:
        """Get value without locking (read-only, not guaranteed consistent)."""
        return self.value
        
    def is_async_context(self) -> bool:
        """Check if we're in an async context.""" 
        return self._lock.is_async_context()
