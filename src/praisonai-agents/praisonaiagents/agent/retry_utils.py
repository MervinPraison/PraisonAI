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
    jitter_ratio: float = 0.5    # Jitter as fraction of delay added on top of base (0.0-1.0)
    max_retries: int = 3         # Maximum retry attempts
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if not (0 <= self.jitter_ratio <= 1):
            raise ValueError("jitter_ratio must be between 0 and 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


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
        jitter_ratio: Jitter ratio (0.0-1.0), fraction of delay added as positive jitter
    
    Returns:
        Delay in seconds with jitter applied
    
    Example:
        >>> # Attempt 0: ~5s, Attempt 1: ~10s, Attempt 2: ~20s
        >>> delay = jittered_backoff(1, base_delay=5.0, max_delay=120.0, jitter_ratio=0.5)
    """
    # Exponential backoff: base * 2^attempt
    delay = min(base_delay * (2 ** max(0, attempt)), max_delay)
    
    # Apply jitter: delay + uniform(0, jitter_ratio * delay) for additive positive jitter
    if jitter_ratio > 0:
        jitter_range = delay * jitter_ratio
        jitter = random.uniform(0, jitter_range)  # Positive additive jitter only
        delay = max(0.1, min(delay + jitter, max_delay))  # Clamp again after jitter
    
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