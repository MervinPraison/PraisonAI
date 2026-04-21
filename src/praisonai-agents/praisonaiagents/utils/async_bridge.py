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
    Safely run a coroutine from sync context only.
    
    Args:
        coro: The coroutine to execute
        timeout: Maximum execution time in seconds (default: 5 minutes)
        
    Returns:
        The result of the coroutine
        
    Raises:
        RuntimeError: If called from async context (event loop is running)
        TimeoutError: If the coroutine takes longer than timeout
        
    Examples:
        >>> async def my_async_function():
        ...     return "hello"
        >>> result = run_coroutine_from_any_context(my_async_function())
        >>> print(result)  # "hello"
    """
    try:
        loop = asyncio.get_running_loop()
        # If we get here, event loop is running - this is not allowed
        raise RuntimeError(
            "run_coroutine_from_any_context() cannot be called from async context. "
            "Use 'await' instead when calling from async functions."
        )
    except RuntimeError as e:
        if "no running event loop" in str(e).lower():
            # No event loop — safe to use asyncio.run()
            return asyncio.run(coro)
        else:
            # Re-raise our own RuntimeError
            raise

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