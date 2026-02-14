"""
Resilience utilities for PraisonAI bots.

Provides exponential backoff, recoverable error detection,
and connection monitoring primitives.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BackoffPolicy:
    """Exponential backoff configuration.
    
    Attributes:
        initial_ms: Initial delay in milliseconds
        max_ms: Maximum delay in milliseconds
        factor: Multiplicative factor per attempt
        jitter: Random jitter fraction (0.0 - 1.0)
        max_attempts: Max retry attempts (0 = unlimited)
    """
    
    initial_ms: float = 2000.0
    max_ms: float = 30000.0
    factor: float = 1.8
    jitter: float = 0.25
    max_attempts: int = 0


# Default policies
TELEGRAM_BACKOFF = BackoffPolicy(initial_ms=2000, max_ms=30000, factor=1.8, jitter=0.25)
DISCORD_BACKOFF = BackoffPolicy(initial_ms=3000, max_ms=60000, factor=2.0, jitter=0.2)
SLACK_BACKOFF = BackoffPolicy(initial_ms=2000, max_ms=30000, factor=1.5, jitter=0.3)
WHATSAPP_BACKOFF = BackoffPolicy(initial_ms=5000, max_ms=60000, factor=2.0, jitter=0.2)


def compute_backoff(policy: BackoffPolicy, attempt: int) -> float:
    """Compute delay for a given attempt number.
    
    Args:
        policy: Backoff configuration
        attempt: Attempt number (1-based)
        
    Returns:
        Delay in seconds
    """
    base_ms = policy.initial_ms * (policy.factor ** (attempt - 1))
    capped_ms = min(base_ms, policy.max_ms)
    
    if policy.jitter > 0:
        jitter_range = capped_ms * policy.jitter
        capped_ms += random.uniform(-jitter_range, jitter_range)
    
    return max(0, capped_ms / 1000.0)


# Common recoverable error patterns across platforms
_RECOVERABLE_PATTERNS: Set[str] = {
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "connection aborted",
    "network unreachable",
    "network is unreachable",
    "temporary failure",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "rate limit",
    "rate_limited",
    "internal server error",
    "server error",
    "eof occurred",
    "broken pipe",
    "reset by peer",
    "name resolution",
    "dns resolution",
    "ssl",
    "certificate",
}

# Telegram-specific patterns
_TELEGRAM_RECOVERABLE: Set[str] = {
    "getupdates",
    "conflict",
    "terminated by other",
    "restart",
    "flood",
    "retry after",
    "webhook",
}


def is_recoverable_error(err: BaseException, platform: str = "") -> bool:
    """Check if an error is likely transient/recoverable.
    
    Args:
        err: The exception to check
        platform: Optional platform name for platform-specific checks
        
    Returns:
        True if the error is likely transient
    """
    msg = str(err).lower()
    err_type = type(err).__name__.lower()
    
    # Check common patterns
    for pattern in _RECOVERABLE_PATTERNS:
        if pattern in msg or pattern in err_type:
            return True
    
    # Platform-specific checks
    if platform == "telegram":
        for pattern in _TELEGRAM_RECOVERABLE:
            if pattern in msg:
                return True
        # HTTP 409 = getUpdates conflict (another bot instance)
        if hasattr(err, 'error_code') and getattr(err, 'error_code', None) == 409:
            return True
    
    # Check for common HTTP status codes
    status = getattr(err, 'status', None) or getattr(err, 'status_code', None)
    if isinstance(status, int) and status in (408, 429, 500, 502, 503, 504):
        return True
    
    # asyncio timeouts
    if isinstance(err, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True
    
    return False


def is_conflict_error(err: BaseException) -> bool:
    """Check if error is a Telegram getUpdates 409 conflict.
    
    This happens when another bot instance is using the same token.
    """
    msg = str(err).lower()
    status = getattr(err, 'error_code', None) or getattr(err, 'status_code', None)
    
    if status == 409:
        return True
    if "409" in msg and "conflict" in msg:
        return True
    if "getupdates" in msg and ("conflict" in msg or "terminated" in msg):
        return True
    
    return False


async def sleep_with_abort(seconds: float, abort_signal: Optional[asyncio.Event] = None) -> bool:
    """Sleep for a duration, but wake early if abort is signaled.
    
    Args:
        seconds: Duration to sleep
        abort_signal: Optional event that cancels the sleep
        
    Returns:
        True if sleep completed normally, False if aborted
    """
    if abort_signal is None:
        await asyncio.sleep(seconds)
        return True
    
    try:
        await asyncio.wait_for(abort_signal.wait(), timeout=seconds)
        return False  # Aborted
    except asyncio.TimeoutError:
        return True  # Normal completion


@dataclass
class ConnectionMonitor:
    """Tracks connection health with automatic backoff.
    
    Attributes:
        platform: Platform name for error classification
        policy: Backoff policy for retries
        attempt: Current retry attempt count
        last_error: Last error encountered
        last_error_time: Timestamp of last error
        total_recoveries: Total successful recoveries
    """
    
    platform: str = ""
    policy: BackoffPolicy = field(default_factory=BackoffPolicy)
    attempt: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    total_recoveries: int = 0
    
    def record_success(self) -> None:
        """Record a successful operation, resetting backoff."""
        if self.attempt > 0:
            self.total_recoveries += 1
            logger.info(
                f"[{self.platform}] Connection recovered after "
                f"{self.attempt} attempt(s)"
            )
        self.attempt = 0
        self.last_error = None
        self.last_error_time = None
    
    def record_error(self, err: BaseException) -> float:
        """Record an error and compute next delay.
        
        Args:
            err: The error that occurred
            
        Returns:
            Delay in seconds before next retry
        """
        self.attempt += 1
        self.last_error = str(err)
        self.last_error_time = time.time()
        
        delay = compute_backoff(self.policy, self.attempt)
        
        logger.warning(
            f"[{self.platform}] Error (attempt {self.attempt}): "
            f"{self.last_error}; retrying in {delay:.1f}s"
        )
        
        return delay
    
    def should_retry(self) -> bool:
        """Check if we should retry based on policy."""
        if self.policy.max_attempts <= 0:
            return True  # Unlimited
        return self.attempt < self.policy.max_attempts
    
    def to_dict(self) -> dict:
        """Serialize for status/health reporting."""
        return {
            "platform": self.platform,
            "attempt": self.attempt,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "total_recoveries": self.total_recoveries,
            "max_attempts": self.policy.max_attempts,
        }
