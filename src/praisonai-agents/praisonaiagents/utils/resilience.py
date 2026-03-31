"""
Centralized resilience and retry policies for PraisonAI Agents.
This module provides standard exponential backoff decorators to handle transient failures.
"""

import asyncio
import random
import time
from functools import wraps
from typing import Any, Callable, Tuple, Type, Union

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    max_backoff_in_seconds: float = 30.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,),
    jitter_factor: float = 0.25,
) -> Callable:
    """
    Synchronous exponential backoff decorator with jitter to prevent thundering herd.

    Args:
        retries: Maximum number of retry attempts.
        backoff_in_seconds: Initial backoff base in seconds.
        max_backoff_in_seconds: Maximum allowed backoff delay in seconds.
        exceptions: Exceptions to catch and retry (can be tuple of types).
        jitter_factor: Randomness factor (e.g., 0.25 = ±25% random jitter).
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= retries:
                        logger.error(
                            f"Execution failed permanently after {attempt} retries "
                            f"in '{func.__name__}': {str(e)}",
                            exc_info=True
                        )
                        raise

                    # Calculate exponential backoff
                    delay = backoff_in_seconds * (2 ** attempt)
                    delay = min(delay, max_backoff_in_seconds)

                    # Add random jitter
                    jitter_range = delay * jitter_factor
                    delay = delay + random.uniform(-jitter_range, jitter_range)
                    delay = max(0.0, delay)
                    
                    attempt += 1
                    logger.warning(
                        f"Transient error '{e.__class__.__name__}' in '{func.__name__}'. "
                        f"Retrying in {delay:.2f}s (Attempt {attempt}/{retries})..."
                    )
                    time.sleep(delay)

        return wrapper

    return decorator


def async_retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    max_backoff_in_seconds: float = 30.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,),
    jitter_factor: float = 0.25,
) -> Callable:
    """
    Asynchronous exponential backoff decorator with jitter.
    
    Identical semantics to `retry_with_backoff` but uses asyncio.sleep
    for non-blocking concurrent multi-agent executions.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= retries:
                        logger.error(
                            f"Async execution failed permanently after {attempt} retries "
                            f"in '{func.__name__}': {str(e)}",
                            exc_info=True
                        )
                        raise

                    # Calculate exponential backoff
                    delay = backoff_in_seconds * (2 ** attempt)
                    delay = min(delay, max_backoff_in_seconds)

                    # Add random jitter
                    jitter_range = delay * jitter_factor
                    delay = delay + random.uniform(-jitter_range, jitter_range)
                    delay = max(0.0, delay)
                    
                    attempt += 1
                    logger.warning(
                        f"Transient async error '{e.__class__.__name__}' in '{func.__name__}'. "
                        f"Retrying in {delay:.2f}s (Attempt {attempt}/{retries})..."
                    )
                    await asyncio.sleep(delay)

        return wrapper

    return decorator
