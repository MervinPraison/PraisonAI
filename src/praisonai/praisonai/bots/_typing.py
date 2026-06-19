"""
Typing indicator management for bot channels.

Provides a unified typing indicator lifecycle with keepalive,
circuit breaker, and safety TTL features.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots.protocols import ChannelCapabilities

logger = logging.getLogger(__name__)


class BotAdapter(Protocol):
    """Protocol for bot adapters that support typing indicators."""
    
    @property
    def capabilities(self) -> "ChannelCapabilities":
        """Get channel capabilities."""
        ...
    
    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator."""
        ...


@dataclass
class TypingConfig:
    """Configuration for typing indicators."""
    
    enabled: bool = True
    keepalive_interval: float = 5.0  # Resend typing every N seconds
    max_duration: float = 60.0  # Maximum typing duration (safety TTL)
    max_consecutive_failures: int = 3  # Circuit breaker threshold
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TypingConfig":
        """Create config from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            keepalive_interval=data.get("keepalive_interval", 5.0),
            max_duration=data.get("max_duration", 60.0),
            max_consecutive_failures=data.get("max_consecutive_failures", 3),
        )


class TypingManager:
    """
    Manages typing indicator lifecycle for bot channels.
    
    Features:
    - Keepalive: Automatically resends typing indicator at intervals
    - Circuit breaker: Stops after consecutive failures
    - Safety TTL: Automatically stops after max duration
    - Graceful cleanup: Ensures typing stops even on errors
    
    Usage:
        async with TypingManager(adapter, channel_id) as typing:
            # Typing indicator active while in context
            await long_running_operation()
        # Typing automatically stopped
        
        # Or manually:
        typing = TypingManager(adapter, channel_id)
        await typing.start()
        # ... do work ...
        await typing.stop()
    """
    
    def __init__(
        self,
        adapter: BotAdapter,
        channel_id: str,
        config: Optional[TypingConfig] = None,
    ):
        self._adapter = adapter
        self._channel_id = channel_id
        self._config = config or TypingConfig()
        
        # State
        self._task: Optional[asyncio.Task] = None
        self._start_time: float = 0
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False
        
        # Check if typing is supported
        caps = adapter.capabilities
        self._supported = caps.get("typing", False) and self._config.enabled
        
        logger.debug(
            "TypingManager initialized for channel %s, typing_supported=%s",
            channel_id, self._supported
        )
    
    async def start(self) -> None:
        """Start sending typing indicators."""
        if not self._supported or self._task or self._circuit_open:
            return
        
        self._start_time = time.monotonic()
        self._consecutive_failures = 0
        
        async def _typing_loop():
            """Keepalive loop for typing indicators."""
            try:
                while True:
                    # Check safety TTL
                    elapsed = time.monotonic() - self._start_time
                    if elapsed > self._config.max_duration:
                        logger.warning(
                            "TypingManager exceeded max duration (%ds), stopping",
                            self._config.max_duration
                        )
                        break
                    
                    # Send typing indicator
                    try:
                        await self._adapter.send_typing(self._channel_id)
                        self._consecutive_failures = 0
                        logger.debug("TypingManager sent typing to %s", self._channel_id)
                        
                    except Exception as e:
                        self._consecutive_failures += 1
                        logger.debug(
                            "TypingManager failed to send typing (failure %d/%d): %s",
                            self._consecutive_failures,
                            self._config.max_consecutive_failures,
                            e
                        )
                        
                        # Circuit breaker
                        if self._consecutive_failures >= self._config.max_consecutive_failures:
                            logger.warning(
                                "TypingManager circuit breaker triggered after %d failures",
                                self._consecutive_failures
                            )
                            self._circuit_open = True
                            break
                    
                    # Wait for next keepalive
                    await asyncio.sleep(self._config.keepalive_interval)
                    
            except asyncio.CancelledError:
                logger.debug("TypingManager cancelled for %s", self._channel_id)
                raise
        
        # Start the loop
        self._task = asyncio.create_task(_typing_loop())
        logger.debug("TypingManager started for %s", self._channel_id)
    
    async def stop(self) -> None:
        """Stop sending typing indicators."""
        if not self._task:
            return
        
        # Cancel the task
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        
        self._task = None
        logger.debug("TypingManager stopped for %s", self._channel_id)
    
    @property
    def is_active(self) -> bool:
        """Check if typing is currently active."""
        return bool(self._task and not self._task.done())
    
    @property
    def duration(self) -> float:
        """Get current typing duration in seconds."""
        if not self._start_time:
            return 0
        return time.monotonic() - self._start_time
    
    async def __aenter__(self) -> "TypingManager":
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.stop()
    
    def reset_circuit(self) -> None:
        """Reset the circuit breaker.
        
        Use this to retry typing after a circuit breaker trip.
        """
        self._circuit_open = False
        self._consecutive_failures = 0
        logger.debug("TypingManager circuit reset for %s", self._channel_id)