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
        self._channel_last_send: Dict[str, float] = {}
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
        async with self._lock:
            now = time.monotonic()
            
            # Refill tokens based on elapsed time
            elapsed = now - self._last_refill
            self._tokens = min(
                self._config.burst_size,
                self._tokens + elapsed * self._config.messages_per_second
            )
            self._last_refill = now
            
            # Wait for global token
            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._config.messages_per_second
                logger.debug(f"Rate limit: waiting {wait_time:.3f}s for global token")
                await asyncio.sleep(wait_time)
                self._tokens = 1.0
            
            # Consume token
            self._tokens -= 1.0
            
            # Per-channel delay
            if channel_id:
                last_send = self._channel_last_send.get(channel_id, 0.0)
                channel_elapsed = now - last_send
                if channel_elapsed < self._config.per_channel_delay:
                    wait_time = self._config.per_channel_delay - channel_elapsed
                    logger.debug(f"Rate limit: waiting {wait_time:.3f}s for channel {channel_id}")
                    await asyncio.sleep(wait_time)
                self._channel_last_send[channel_id] = time.monotonic()
    
    def reset(self) -> None:
        """Reset rate limiter state."""
        self._tokens = float(self._config.burst_size)
        self._last_refill = time.monotonic()
        self._channel_last_send.clear()


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
