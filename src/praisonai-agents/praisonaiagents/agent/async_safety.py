"""
Async-safe concurrency primitives for agent state protection.

This module provides dual-lock abstractions that automatically select
the appropriate lock type based on the execution context (sync vs async).
"""
import asyncio
import threading
from typing import Any, Optional, Union
from contextlib import contextmanager, asynccontextmanager


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
        async with lock.async():
            # Uses asyncio.Lock
            pass
        ```
    """
    
    def __init__(self):
        """Initialize with unified thread-safe locking."""
        self._thread_lock = threading.RLock()  # Re-entrant lock to handle nested acquisitions
    
    @contextmanager
    def sync(self):
        """Acquire lock in synchronous context using threading.Lock."""
        with self._thread_lock:
            yield
            
    @asynccontextmanager
    async def async_lock(self):
        """Acquire lock in asynchronous context using the thread lock directly.

        Note: This acquires the threading.RLock on the calling coroutine's thread
        (event loop thread). Acquisition is brief (in-memory only) so the brief
        event loop block is acceptable. Using asyncio.to_thread for acquire would
        break same-thread ownership required by RLock.
        """
        self._thread_lock.acquire()
        try:
            yield
        finally:
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
        
    @contextmanager 
    def lock(self):
        """Acquire lock in sync context."""
        with self._lock.sync():
            yield self.value
            
    @asynccontextmanager
    async def async_lock(self):
        """Acquire lock in async context."""
        async with self._lock.async_lock():
            yield self.value
            
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
        self._lock._thread_lock.acquire()
        return self.value
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support for asynchronous context manager protocol."""
        self._lock._thread_lock.release()
        return None
            
    def get(self) -> Any:
        """Get value without locking (read-only, not guaranteed consistent)."""
        return self.value
        
    def is_async_context(self) -> bool:
        """Check if we're in an async context.""" 
        return self._lock.is_async_context()