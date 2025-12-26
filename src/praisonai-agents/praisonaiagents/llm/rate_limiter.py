"""
Rate Limiter for PraisonAI Agents.

Provides token bucket rate limiting for LLM API calls.

Zero Performance Impact:
- When rate_limiter is None, no overhead
- Uses monotonic clock for accuracy
- Injectable clock/sleep for deterministic testing

Usage:
    from praisonaiagents.llm import RateLimiter
    from praisonaiagents import Agent
    
    limiter = RateLimiter(requests_per_minute=60)
    agent = Agent(name="Test", rate_limiter=limiter)
"""

import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls.
    
    Uses the token bucket algorithm:
    - Tokens are added at a fixed rate (requests_per_minute / 60 per second)
    - Each request consumes one token
    - If no tokens available, wait until one is available
    - Burst allows multiple requests in quick succession
    
    Args:
        requests_per_minute: Maximum requests per minute
        tokens_per_minute: Optional token-based rate limiting (for future use)
        burst: Maximum burst size (default: 1)
    
    Example:
        limiter = RateLimiter(requests_per_minute=60)  # 1 req/sec
        limiter.acquire()  # Blocks if rate exceeded
        
        # Async usage
        await limiter.acquire_async()
    """
    requests_per_minute: int
    tokens_per_minute: Optional[int] = None
    burst: int = 1
    
    # Internal state
    _tokens: float = field(default=None, init=False, repr=False)
    _last_update: float = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default=None, init=False, repr=False)
    
    # Injectable functions for testing
    _get_time: Callable[[], float] = field(default=None, init=False, repr=False)
    _sleep: Callable[[float], None] = field(default=None, init=False, repr=False)
    _async_sleep: Callable[[float], None] = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Initialize internal state."""
        self._tokens = float(self.burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
        
        # Default implementations (can be overridden for testing)
        if self._get_time is None:
            self._get_time = time.monotonic
        if self._sleep is None:
            self._sleep = time.sleep
        if self._async_sleep is None:
            self._async_sleep = asyncio.sleep
    
    @property
    def _rate(self) -> float:
        """Tokens per second."""
        return self.requests_per_minute / 60.0
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = self._get_time()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self._rate)
        self._last_update = now
    
    def _wait_time(self) -> float:
        """Calculate time to wait for next token."""
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._rate
    
    def acquire(self) -> None:
        """Acquire a token, blocking if necessary.
        
        This is the synchronous version. Use acquire_async() for async code.
        """
        self._refill()
        
        wait = self._wait_time()
        if wait > 0:
            self._sleep(wait)
            self._refill()
        
        self._tokens -= 1.0
    
    async def acquire_async(self) -> None:
        """Acquire a token asynchronously, waiting if necessary.
        
        This is the async version. Use acquire() for sync code.
        """
        async with self._lock:
            self._refill()
            
            wait = self._wait_time()
            if wait > 0:
                await self._async_sleep(wait)
                self._refill()
            
            self._tokens -= 1.0
    
    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking.
        
        Returns:
            True if token acquired, False if rate limit exceeded
        """
        self._refill()
        
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
    
    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        self._tokens = float(self.burst)
        self._last_update = self._get_time()
    
    @property
    def available_tokens(self) -> float:
        """Get current available tokens (for monitoring)."""
        self._refill()
        return self._tokens
    
    def __repr__(self) -> str:
        return f"RateLimiter(rpm={self.requests_per_minute}, burst={self.burst})"
