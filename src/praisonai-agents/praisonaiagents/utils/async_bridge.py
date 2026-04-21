"""
Async/sync bridge utility for safely running coroutines from any context.

This module provides utilities to safely bridge between async and sync contexts,
ensuring no RuntimeError: "This event loop is already running" crashes.
"""

import asyncio
import concurrent.futures
import logging
from typing import Any, Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

def run_coroutine_from_any_context(coro: Awaitable[T], timeout: float = 300) -> T:
    """
    Safely run a coroutine from either sync or async context.
    
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
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop — safe to use asyncio.run()
        return asyncio.run(coro)

    # Event loop exists — run in a dedicated thread to avoid deadlock
    # This ensures we never nest event loops or block the current one
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        def _run():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        future = pool.submit(_run)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(f"Coroutine execution timed out after {timeout}s")
            raise TimeoutError(f"Coroutine execution timed out after {timeout} seconds")

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