"""
Utility functions for approval handling.

Provides reusable async-to-sync bridging logic to prevent code duplication
across the approval system.
"""

import asyncio
import concurrent.futures
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar('T')


def run_coroutine_safely(
    coro: Awaitable[T], 
    timeout: Optional[float] = None
) -> T:
    """
    Run a coroutine safely, handling both sync and async contexts.
    
    This function detects if an event loop is already running and uses a
    ThreadPoolExecutor as a fallback to avoid RuntimeError. It respects
    timeout semantics consistently across both code paths.
    
    Args:
        coro: The coroutine to execute
        timeout: Timeout in seconds. None means indefinite wait.
        
    Returns:
        The result of the coroutine
        
    Raises:
        TimeoutError: If the operation times out
        Any exception raised by the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # We're in an async context - use thread pool to avoid RuntimeError
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        
        # Wrap the coroutine with timeout handling inside the thread
        def run_with_timeout():
            if timeout is not None and timeout > 0:
                return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
            else:
                return asyncio.run(coro)
        
        future = pool.submit(run_with_timeout)
        try:
            # Don't use timeout on Future.result() since we handle timeout
            # inside the coroutine via asyncio.wait_for
            result = future.result(timeout=None if timeout is None or timeout == 0 else timeout)
            return result
        finally:
            # Properly shut down the executor without waiting for threads
            pool.shutdown(wait=False, cancel_futures=True)
    else:
        # No running event loop - use asyncio.run directly
        if timeout is not None and timeout > 0:
            return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        else:
            return asyncio.run(coro)