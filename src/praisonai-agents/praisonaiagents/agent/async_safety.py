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
        """Initialize with separate threading and asyncio locks."""
        self._thread_lock = threading.RLock()  # Re-entrant lock to handle nested acquisitions
        self._async_locks = WeakKeyDictionary()  # Per-event-loop async locks

    def __deepcopy__(self, memo):
        """Return an unlocked primitive with no event-loop state sharing."""
        result = type(self)()
        memo[id(self)] = result
        return result
    
    @contextmanager
    def sync(self):
        """Acquire lock in synchronous context using threading.Lock."""
        with self._thread_lock:
            yield
            
    def _get_async_lock(self):
        """Get or create an asyncio.Lock for the current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("async_lock() must be called from an async context")
        
        if loop not in self._async_locks:
            self._async_locks[loop] = asyncio.Lock()
        return self._async_locks[loop]

    @asynccontextmanager
    async def async_lock(self):
        """Acquire lock in asynchronous context using asyncio.Lock.
        
        Uses a per-event-loop asyncio.Lock to ensure proper async coordination
        without blocking the event loop or violating thread ownership semantics.
        """
        async_lock = self._get_async_lock()
        async with async_lock:
            yield
            
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
        async with self._lock.async_lock():
            self._begin_async_access()
            try:
                yield self.value
            finally:
                self._end_async_access()

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
        self._lock._thread_lock.acquire()
        return self.value
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support for synchronous context manager protocol (backward compatibility)."""
        self._lock._thread_lock.release()
        return None
        
    async def __aenter__(self):
        """Support for asynchronous context manager protocol."""
        async_lock = self._lock._get_async_lock()
        await async_lock.acquire()
        try:
            self._begin_async_access()
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
            async_lock.release()
        return None
            
    def get(self) -> Any:
        """Get value without locking (read-only, not guaranteed consistent)."""
        return self.value
        
    def is_async_context(self) -> bool:
        """Check if we're in an async context.""" 
        return self._lock.is_async_context()
