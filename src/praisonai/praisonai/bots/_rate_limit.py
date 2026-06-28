"""
Rate Limiting Utilities for Bot Adapters.

Provides platform-aware rate limiting to prevent 429 errors from messaging APIs.

Platform limits (as of 2024):
- Telegram: ~30 messages/second to different users, stricter per-chat
- Discord: 5 messages per 5 seconds per channel (1 msg/sec effective)
- Slack: 1 message per second per channel
- WhatsApp: ~80 messages/second (Cloud API), varies for Web
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.
    
    Attributes:
        messages_per_second: Maximum messages per second (global)
        per_channel_delay: Minimum delay between messages to same channel (seconds)
        burst_size: Number of messages allowed in a burst before throttling
    """
    messages_per_second: float = 1.0
    per_channel_delay: float = 1.0
    burst_size: int = 5


# Platform-specific defaults
PLATFORM_LIMITS: Dict[str, RateLimitConfig] = {
    "telegram": RateLimitConfig(messages_per_second=25.0, per_channel_delay=0.05, burst_size=30),
    "discord": RateLimitConfig(messages_per_second=1.0, per_channel_delay=1.0, burst_size=5),
    "slack": RateLimitConfig(messages_per_second=1.0, per_channel_delay=1.0, burst_size=1),
    "whatsapp": RateLimitConfig(messages_per_second=50.0, per_channel_delay=0.1, burst_size=80),
}


class RateLimiter:
    """Async rate limiter with per-channel tracking.
    
    Uses token bucket algorithm for global rate and per-channel delays.
    
    Example:
        limiter = RateLimiter.for_platform("telegram")
        
        async def send(channel_id, msg):
            await limiter.acquire(channel_id)
            await api.send_message(channel_id, msg)
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize rate limiter.
        
        Args:
            config: Rate limit configuration. Defaults to 1 msg/sec.
        """
        self._config = config or RateLimitConfig()
        self._tokens = float(self._config.burst_size)
        self._last_refill = time.monotonic()
        self._channel_last_send: "OrderedDict[str, float]" = OrderedDict()
        # Adaptive penalties: channel_id -> monotonic timestamp until which
        # sends to that channel must be held off (set via penalise()).
        self._channel_penalty_until: "OrderedDict[str, float]" = OrderedDict()
        # Global penalty window applied across all channels (e.g. a global 429).
        self._global_penalty_until: float = 0.0
        self._lock = asyncio.Lock()
    
    @classmethod
    def for_platform(cls, platform: str) -> "RateLimiter":
        """Create a rate limiter with platform-specific defaults.
        
        Args:
            platform: Platform name (telegram, discord, slack, whatsapp)
            
        Returns:
            Configured RateLimiter instance
        """
        config = PLATFORM_LIMITS.get(platform.lower(), RateLimitConfig())
        return cls(config)
    
    async def acquire(self, channel_id: Optional[str] = None) -> None:
        """Wait until rate limit allows sending.
        
        Args:
            channel_id: Optional channel ID for per-channel limiting
        """
        # Phase 1: under lock, compute waits + reserve token + update last_send.
        async with self._lock:
            now = time.monotonic()
            
            # Refill tokens based on elapsed time
            elapsed = now - self._last_refill
            self._tokens = min(
                self._config.burst_size,
                self._tokens + elapsed * self._config.messages_per_second
            )
            self._last_refill = now
            
            global_wait = 0.0
            if self._tokens < 1.0:
                global_wait = (1.0 - self._tokens) / self._config.messages_per_second
                self._tokens = 1.0  # reserve one future token
                # Move refill anchor forward to the reservation time so
                # concurrent callers cannot reuse the same future interval.
                self._last_refill = now + global_wait
            self._tokens -= 1.0
            
            # Honour any active global penalty window (e.g. a platform-wide 429).
            if self._global_penalty_until > now + global_wait:
                global_wait = self._global_penalty_until - now
            
            channel_wait = 0.0
            if channel_id:
                last = self._channel_last_send.pop(channel_id, 0.0)
                projected_now = now + global_wait
                elapsed = projected_now - last
                if elapsed < self._config.per_channel_delay:
                    channel_wait = self._config.per_channel_delay - elapsed
                # Honour an active per-channel penalty window (server Retry-After).
                penalty_until = self._channel_penalty_until.get(channel_id, 0.0)
                if penalty_until > projected_now + channel_wait:
                    channel_wait = penalty_until - projected_now
                elif penalty_until and penalty_until <= now:
                    self._channel_penalty_until.pop(channel_id, None)
                # LRU touch + bounded insertion
                self._channel_last_send[channel_id] = projected_now + channel_wait
                while len(self._channel_last_send) > 4096:
                    self._channel_last_send.popitem(last=False)

        # Phase 2: sleep OUTSIDE the lock so other channels proceed concurrently.
        total_wait = global_wait + channel_wait
        if total_wait > 0:
            logger.debug(f"Rate limit: waiting {total_wait:.3f}s for channel {channel_id}")
            await asyncio.sleep(total_wait)
    
    async def penalise(self, channel_id: Optional[str], seconds: float) -> None:
        """Widen a lane for ``seconds`` after a server throttle signal.

        Called when a 429 / flood_wait is observed (see
        ``server_retry_after``). Subsequent :meth:`acquire` calls for the
        affected channel (or globally when ``channel_id`` is None) will hold
        off until the window elapses, so the next sends do not immediately
        re-trip the platform's rate limit.

        Args:
            channel_id: Channel to penalise, or None for a global penalty.
            seconds: Duration of the hold-off window in seconds.
        """
        if seconds <= 0:
            return
        async with self._lock:
            until = time.monotonic() + seconds
            if channel_id:
                cur = self._channel_penalty_until.pop(channel_id, 0.0)
                self._channel_penalty_until[channel_id] = max(cur, until)
                while len(self._channel_penalty_until) > 4096:
                    self._channel_penalty_until.popitem(last=False)
            else:
                self._global_penalty_until = max(self._global_penalty_until, until)
        logger.debug(
            f"Rate limit penalty: holding off {seconds:.3f}s for "
            f"channel {channel_id or '<global>'}"
        )

    def reset(self) -> None:
        """Reset rate limiter state."""
        self._tokens = float(self._config.burst_size)
        self._last_refill = time.monotonic()
        self._channel_last_send.clear()
        self._channel_penalty_until.clear()
        self._global_penalty_until = 0.0


def get_rate_limiter(platform: str) -> RateLimiter:
    """Get a rate limiter for the specified platform.
    
    This is a convenience function that creates a new limiter each time.
    For persistent limiting, create and store a RateLimiter instance.
    
    Args:
        platform: Platform name
        
    Returns:
        Configured RateLimiter
    """
    return RateLimiter.for_platform(platform)
