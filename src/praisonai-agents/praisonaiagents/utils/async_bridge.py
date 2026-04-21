"""
Async/sync bridge utility for safely running coroutines from any context.

This module provides utilities to safely bridge between async and sync contexts,
ensuring no RuntimeError: "This event loop is already running" crashes.
Based on the proven implementation in praisonai/_async_bridge.py.
"""

import asyncio
import logging
import threading
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from typing import Any, Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _ensure_background_loop() -> asyncio.AbstractEventLoop:
    """Ensure a background event loop exists and return it."""
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            t = threading.Thread(target=_loop.run_forever, name="praisonaiagents-async", daemon=True)
            t.start()
        return _loop


def run_coroutine_from_any_context(coro: Awaitable[T], timeout: float = 300) -> T:
    """
    Safely run a coroutine from either sync or async context.
    
    This function automatically detects if there's already a running event loop
    and handles the execution appropriately:
    - If no loop is running: uses asyncio.run() (fastest path)
    - If a loop is running: schedules on background loop (safe path)
    
    Args:
        coro: The coroutine to execute
        timeout: Maximum execution time in seconds (default: 5 minutes)
        
    Returns:
        The result of the coroutine
        
    Raises:
        TimeoutError: If the coroutine takes longer than timeout
        RuntimeError: If the coroutine fails to execute
        
    Examples:
        >>> async def my_async_function():
        ...     return "hello"
        >>> result = run_coroutine_from_any_context(my_async_function())
        >>> print(result)  # "hello"
    """
    try:
        # Check if we're already in an event loop
        asyncio.get_running_loop()
        # If we get here, we're in an async context - use background loop
        background_loop = _ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(coro, background_loop)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as e:
            logger.error(f"Coroutine execution timed out after {timeout}s")
            raise TimeoutError(f"Coroutine execution timed out after {timeout} seconds") from e
    except RuntimeError:
        # No event loop running - safe to use asyncio.run() directly
        return asyncio.run(coro)

def is_async_context() -> bool:
    """
    Check if we are currently in an async context (event loop is running).
    
    Returns:
        True if an event loop is running, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False

async def run_sync_in_executor(func, *args, **kwargs) -> Any:
    """
    Run a sync function in a thread executor to avoid blocking the event loop.
    
    Args:
        func: The synchronous function to run
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        The result of the function
    """
    loop = asyncio.get_running_loop()
    
    # For functions with kwargs, we need to use a wrapper
    if kwargs:
        def wrapper():
            return func(*args, **kwargs)
        return await loop.run_in_executor(None, wrapper)
    else:
        return await loop.run_in_executor(None, func, *args)