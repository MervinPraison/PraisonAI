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

    # Request-based limiting
    limiter = RateLimiter(requests_per_minute=60)
    agent = Agent(name="Test", rate_limiter=limiter)

    # Token-based limiting (for API token quotas)
    limiter = RateLimiter(tokens_per_minute=1000000)
    agent = Agent(name="Test", rate_limiter=limiter)
"""

import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls.

    Uses the token bucket algorithm:
    - Tokens are added at a fixed rate (requests_per_minute / 60 per second)
    - Each request consumes one token
    - If no tokens available, wait until one is available
    - Burst allows multiple requests in quick succession

    Args:
        requests_per_minute: Maximum requests per minute (default: None)
        tokens_per_minute: Maximum API tokens per minute for token-based limiting
        burst: Maximum burst size (default: 1 for requests, auto-calculated for tokens)
        max_retry_delay: Maximum delay in seconds for rate limit retries (default: 120)

    Example:
        # Request-based limiting
        limiter = RateLimiter(requests_per_minute=60)  # 1 req/sec
        limiter.acquire()  # Blocks if rate exceeded

        # Token-based limiting (for API quotas like Gemini)
        limiter = RateLimiter(tokens_per_minute=1000000)  # 1M tokens/min
        limiter.acquire_tokens(5000)  # Request 5000 tokens

        # Async usage
        await limiter.acquire_async()
    """
    requests_per_minute: Optional[int] = None
    tokens_per_minute: Optional[int] = None
    burst: int = 1
    max_retry_delay: int = 120

    # Internal state for request limiting
    _tokens: float = field(default=None, init=False, repr=False)
    _last_update: float = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default=None, init=False, repr=False)

    # Internal state for token-based limiting
    _api_tokens: float = field(default=None, init=False, repr=False)
    _api_tokens_last_update: float = field(default=None, init=False, repr=False)
    _api_tokens_lock: asyncio.Lock = field(default=None, init=False, repr=False)

    # Injectable functions for testing
    _get_time: Callable[[], float] = field(default=None, init=False, repr=False)
    _sleep: Callable[[float], None] = field(default=None, init=False, repr=False)
    _async_sleep: Callable[[float], None] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Initialize internal state."""
        # Request-based limiting
        if self.requests_per_minute is not None:
            self._tokens = float(self.burst)
        else:
            self._tokens = float('inf')
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

        # Token-based limiting
        if self.tokens_per_minute is not None:
            token_burst = max(self.burst, self.tokens_per_minute // 60)
            self._api_tokens = float(token_burst)
        else:
            self._api_tokens = float('inf')
        self._api_tokens_last_update = time.monotonic()
        self._api_tokens_lock = asyncio.Lock()

        # Default implementations (can be overridden for testing)
        if self._get_time is None:
            self._get_time = time.monotonic
        if self._sleep is None:
            self._sleep = time.sleep
        if self._async_sleep is None:
            self._async_sleep = asyncio.sleep

    @property
    def _rate(self) -> float:
        """Requests per second."""
        if self.requests_per_minute is None:
            return float('inf')
        return self.requests_per_minute / 60.0

    @property
    def _token_rate(self) -> float:
        """API tokens per second."""
        if self.tokens_per_minute is None:
            return float('inf')
        return self.tokens_per_minute / 60.0

    def _refill(self) -> None:
        """Refill request tokens based on elapsed time."""
        if self.requests_per_minute is None:
            return
        now = self._get_time()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self._rate)
        self._last_update = now

    def _refill_api_tokens(self) -> None:
        """Refill API tokens based on elapsed time."""
        if self.tokens_per_minute is None:
            return
        now = self._get_time()
        elapsed = now - self._api_tokens_last_update
        token_burst = max(self.burst, self.tokens_per_minute // 60)
        self._api_tokens = min(token_burst, self._api_tokens + elapsed * self._token_rate)
        self._api_tokens_last_update = now

    def _wait_time(self) -> float:
        """Calculate time to wait for next request token."""
        if self.requests_per_minute is None or self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._rate

    def _wait_time_for_tokens(self, num_tokens: int) -> float:
        """Calculate time to wait for API tokens."""
        if self.tokens_per_minute is None or self._api_tokens >= num_tokens:
            return 0.0
        tokens_needed = num_tokens - self._api_tokens
        return tokens_needed / self._token_rate

    def acquire(self) -> None:
        """Acquire a request token, blocking if necessary.

        This is the synchronous version. Use acquire_async() for async code.
        """
        if self.requests_per_minute is None:
            return

        self._refill()

        wait = self._wait_time()
        if wait > 0:
            logger.debug(f"Rate limit: waiting {wait:.2f}s before next request")
            self._sleep(wait)
            self._refill()

        self._tokens -= 1.0

    def acquire_tokens(self, num_tokens: int) -> None:
        """Acquire API tokens, blocking if necessary.

        Args:
            num_tokens: Number of API tokens to acquire

        Note:
            If num_tokens exceeds the burst capacity, this will wait until
            enough tokens accumulate. For very large requests, consider
            splitting into smaller chunks or increasing tokens_per_minute.
        """
        if self.tokens_per_minute is None:
            return

        self._refill_api_tokens()

        wait = self._wait_time_for_tokens(num_tokens)
        if wait > 0:
            # Do NOT cap internal wait time - this ensures correct rate limiting
            # The wait time is calculated based on token refill rate and must be honored
            logger.debug(f"Token limit: waiting {wait:.2f}s for {num_tokens} tokens")
            self._sleep(wait)
            self._refill_api_tokens()

        self._api_tokens -= num_tokens

    async def acquire_async(self) -> None:
        """Acquire a request token asynchronously, waiting if necessary.

        This is the async version. Use acquire() for sync code.
        """
        if self.requests_per_minute is None:
            return

        async with self._lock:
            self._refill()

            wait = self._wait_time()
            if wait > 0:
                logger.debug(f"Rate limit: waiting {wait:.2f}s before next request")
                await self._async_sleep(wait)
                self._refill()

            self._tokens -= 1.0

    async def acquire_tokens_async(self, num_tokens: int) -> None:
        """Acquire API tokens asynchronously.

        Args:
            num_tokens: Number of API tokens to acquire

        Note:
            If num_tokens exceeds the burst capacity, this will wait until
            enough tokens accumulate. For very large requests, consider
            splitting into smaller chunks or increasing tokens_per_minute.
        """
        if self.tokens_per_minute is None:
            return

        async with self._api_tokens_lock:
            self._refill_api_tokens()

            wait = self._wait_time_for_tokens(num_tokens)
            if wait > 0:
                # Do NOT cap internal wait time - this ensures correct rate limiting
                logger.debug(f"Token limit: waiting {wait:.2f}s for {num_tokens} tokens")
                await self._async_sleep(wait)
                self._refill_api_tokens()

            self._api_tokens -= num_tokens

    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking.

        Returns:
            True if token acquired, False if rate limit exceeded
        """
        if self.requests_per_minute is None:
            return True

        self._refill()

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        if self.requests_per_minute is not None:
            self._tokens = float(self.burst)
        self._last_update = self._get_time()

        if self.tokens_per_minute is not None:
            token_burst = max(self.burst, self.tokens_per_minute // 60)
            self._api_tokens = float(token_burst)
        self._api_tokens_last_update = self._get_time()

    def wait_for_retry(self, retry_delay: float) -> None:
        """Wait for a specified retry delay (for handling 429 errors).

        Args:
            retry_delay: Delay in seconds to wait
        """
        delay = min(retry_delay, self.max_retry_delay)
        logger.info(f"Rate limit exceeded, waiting {delay:.1f}s before retry")
        self._sleep(delay)

    async def wait_for_retry_async(self, retry_delay: float) -> None:
        """Asynchronously wait for a specified retry delay.

        Args:
            retry_delay: Delay in seconds to wait
        """
        delay = min(retry_delay, self.max_retry_delay)
        logger.info(f"Rate limit exceeded, waiting {delay:.1f}s before retry")
        await self._async_sleep(delay)

    @property
    def available_tokens(self) -> float:
        """Get current available request tokens (for monitoring)."""
        self._refill()
        return self._tokens

    @property
    def available_api_tokens(self) -> float:
        """Get current available API tokens (for monitoring)."""
        self._refill_api_tokens()
        return self._api_tokens

    def __repr__(self) -> str:
        parts = []
        if self.requests_per_minute is not None:
            parts.append(f"rpm={self.requests_per_minute}")
        if self.tokens_per_minute is not None:
            parts.append(f"tpm={self.tokens_per_minute}")
        parts.append(f"burst={self.burst}")
        return f"RateLimiter({', '.join(parts)})"
