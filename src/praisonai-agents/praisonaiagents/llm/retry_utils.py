"""
Retry utilities for LLM error recovery.

Provides jittered backoff calculations and retry helpers for LLM error recovery.
"""

import random


def jittered_backoff(attempt: int, base: float = 5.0, cap: float = 120.0) -> float:
    """
    Exponential backoff with ±50% jitter.
    
    Prevents thundering herd problems when multiple agents hit rate limits
    simultaneously by adding randomization to retry timing.
    
    Args:
        attempt: Current attempt number (1-based)
        base: Base delay in seconds
        cap: Maximum delay in seconds
        
    Returns:
        Delay in seconds with jitter applied
        
    Examples:
        >>> # Attempt 1: ~2.5-7.5 seconds
        >>> jittered_backoff(1, base=5.0)
        >>> # Attempt 2: ~5.0-15.0 seconds  
        >>> jittered_backoff(2, base=5.0)
        >>> # Attempt 3: ~10.0-30.0 seconds
        >>> jittered_backoff(3, base=5.0)
    """
    if attempt < 1:
        return 0.0
        
    # Exponential backoff: base * (2 ^ (attempt - 1))
    exponential_delay = min(base * (2 ** (attempt - 1)), cap)
    
    # Add ±50% jitter
    jitter_range = 0.5 * exponential_delay
    jitter = random.uniform(-jitter_range, jitter_range)
    
    # Ensure non-negative result
    return max(0.0, exponential_delay + jitter)


def calculate_backoff_with_retry_after(
    retry_after_seconds: float,
    attempt: int,
    base: float = 5.0,
    cap: float = 120.0
) -> float:
    """
    Calculate backoff time considering both retry-after hints and attempt count.
    
    Uses the larger of retry-after hint and jittered exponential backoff
    to respect server hints while still handling repeated failures.
    
    Args:
        retry_after_seconds: Server-suggested retry delay
        attempt: Current attempt number  
        base: Base delay for exponential backoff
        cap: Maximum delay in seconds
        
    Returns:
        Delay in seconds to wait before retry
    """
    exponential_delay = jittered_backoff(attempt, base, cap)
    
    # Use the larger of the two delays
    return max(retry_after_seconds, exponential_delay)