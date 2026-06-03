"""
Retry utilities with jittered exponential backoff for the PraisonAI SDK.

Provides interrupt-aware retry mechanisms for LLM API calls and tool execution
with configurable backoff strategies, jitter, and buffered status reporting.
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class RetryBackoffConfig:
    """Configuration for jittered exponential backoff retry behavior."""
    base_delay: float = 5.0      # Base delay in seconds
    max_delay: float = 120.0     # Maximum delay in seconds  
    jitter_ratio: float = 0.5    # Jitter as fraction of delay (0.0-1.0)
    max_retries: int = 3         # Maximum retry attempts


def jittered_backoff(
    attempt: int,
    *,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    jitter_ratio: float = 0.5,
) -> float:
    """
    Calculate delay for jittered exponential backoff.
    
    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter_ratio: Jitter ratio (0.0-1.0), added/subtracted from base delay
    
    Returns:
        Delay in seconds with jitter applied
    
    Example:
        >>> # Attempt 0: ~5s, Attempt 1: ~10s, Attempt 2: ~20s
        >>> delay = jittered_backoff(1, base_delay=5.0, max_delay=120.0, jitter_ratio=0.5)
    """
    # Exponential backoff: base * 2^attempt
    delay = min(base_delay * (2 ** max(0, attempt)), max_delay)
    
    # Apply jitter: delay ± (jitter_ratio * delay)
    if jitter_ratio > 0:
        jitter_range = delay * jitter_ratio
        jitter = random.uniform(-jitter_range, jitter_range)
        delay = max(0.1, delay + jitter)  # Ensure minimum 100ms delay
    
    return delay


async def interruptible_sleep(
    seconds: float,
    check_interval: float = 0.2,
    interrupt_fn: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Sleep with periodic interruption checks.
    
    Args:
        seconds: Total sleep duration in seconds
        check_interval: How often to check for interruption (seconds)
        interrupt_fn: Function that returns True if sleep should be interrupted
    
    Returns:
        True if completed full sleep, False if interrupted
    
    Example:
        >>> interrupted = await interruptible_sleep(30.0, interrupt_fn=lambda: agent.is_stopped())
    """
    if interrupt_fn is None:
        interrupt_fn = lambda: False
    
    elapsed = 0.0
    while elapsed < seconds:
        if interrupt_fn():
            return False  # Interrupted
        
        sleep_time = min(check_interval, seconds - elapsed)
        await asyncio.sleep(sleep_time)
        elapsed += sleep_time
    
    return True  # Completed full sleep