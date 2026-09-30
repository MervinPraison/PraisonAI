"""
Async/sync bridge utility for safely running coroutines from any context.

This module provides utilities to safely bridge between async and sync contexts,
ensuring no RuntimeError: "This event loop is already running" crashes.
"""

import asyncio
import concurrent.futures
import contextvars
import logging
from typing import Any, Awaitable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

def run_coroutine_from_any_context(coro: Awaitable[T], timeout: Optional[float] = 300) -> T:
    """
    Safely run a coroutine to completion from any context (sync OR inside a
    running event loop).

    - No running loop: run it directly with ``asyncio.run`` (wrapped in
      ``asyncio.wait_for`` when a timeout is set).
    - Running loop (FastAPI, Jupyter, a bot handler calling ``agent.chat()``):
      run it on a dedicated worker thread with its own loop so we never
      deadlock on the caller's loop. The caller's ``contextvars`` are copied
      into that thread so trace/session/approval context set by the caller is
      visible inside the coroutine, and the timeout is enforced *inside* the
      worker loop via ``asyncio.wait_for`` so the caller does not block past
      ``timeout`` waiting on a stuck worker.

    Args:
        coro: The coroutine to execute
        timeout: Maximum execution time in seconds (default: 5 minutes).
            ``None`` disables the timeout.

    Returns:
        The result of the coroutine

    Raises:
        TimeoutError: If the coroutine takes longer than ``timeout``

    Examples:
        >>> async def my_async_function():
        ...     return "hello"
        >>> result = run_coroutine_from_any_context(my_async_function())
        >>> print(result)  # "hello"
    """
    def _wrapped() -> Awaitable[T]:
        return asyncio.wait_for(coro, timeout) if timeout is not None else coro

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — safe to drive it directly on this thread.
        return asyncio.run(_wrapped())

    # A loop is already running on this thread. Offload to a worker thread with
    # its own loop, carrying the caller's contextvars across so context set by
    # the caller (trace/session/approval) is visible inside the coroutine.
    ctx = contextvars.copy_context()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(ctx.run, asyncio.run, _wrapped())
    try:
        # Timeout is enforced inside the worker loop by asyncio.wait_for, so we
        # wait on the result without a second (blocking) timeout here.
        return future.result()
    finally:
        # Never block on a stuck worker: don't wait for it to wind down.
        executor.shutdown(wait=False)

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