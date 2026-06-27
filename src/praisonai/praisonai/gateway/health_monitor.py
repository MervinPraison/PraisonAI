"""
Channel health monitoring for WebSocket Gateway.

Provides proactive health monitoring and auto-recovery for channels
with configurable policies and rate limiting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from praisonaiagents.bots.protocols import (
    HealthReason,
    HealthResult,
    evaluate_channel_health,
)

logger = logging.getLogger(__name__)


@dataclass
class HealthMonitorConfig:
    """Configuration for channel health monitoring."""
    
    interval: float = 300.0  # 5 minutes default
    startup_grace: float = 60.0  # 1 minute grace period for startup
    stale_after: float = 120.0  # 2 minutes without inbound activity = stale
    stuck_after: float = 900.0  # 15 minutes busy with no progress = stuck
    max_restarts_per_hour: int = 10  # Rate limit for restarts
    enabled: bool = True  # Whether monitoring is enabled
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthMonitorConfig":
        """Create config from dictionary."""
        return cls(
            interval=float(data.get("interval", 300.0)),
            startup_grace=float(data.get("startup_grace", 60.0)),
            stale_after=float(data.get("stale_after", 120.0)),
            stuck_after=float(data.get("stuck_after", 900.0)),
            max_restarts_per_hour=int(data.get("max_restarts_per_hour", 10)),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class ChannelRestartHistory:
    """Track restart history for rate limiting."""
    
    timestamps: list[float] = field(default_factory=list)
    cooldown_until: Optional[float] = None
    
    def can_restart(self, max_per_hour: int, current_time: Optional[float] = None) -> bool:
        """Check if channel can be restarted based on rate limits."""
        if current_time is None:
            current_time = time.time()
        
        # Check cooldown
        if self.cooldown_until and current_time < self.cooldown_until:
            return False
        
        # Remove old timestamps (older than 1 hour)
        hour_ago = current_time - 3600
        self.timestamps = [ts for ts in self.timestamps if ts > hour_ago]
        
        # Check rate limit
        return len(self.timestamps) < max_per_hour
    
    def record_restart(self, current_time: Optional[float] = None) -> None:
        """Record a restart attempt."""
        if current_time is None:
            current_time = time.time()
        self.timestamps.append(current_time)
        
        # Set a 5-minute cooldown after each restart
        self.cooldown_until = current_time + 300
    
    def get_restart_count(self, current_time: Optional[float] = None) -> int:
        """Get number of restarts in the past hour."""
        if current_time is None:
            current_time = time.time()
        
        hour_ago = current_time - 3600
        self.timestamps = [ts for ts in self.timestamps if ts > hour_ago]
        return len(self.timestamps)


class ChannelHealthMonitor:
    """Monitors channel health and triggers auto-recovery.
    
    Provides:
    - Periodic health checks for all registered channels
    - Automatic restart of unhealthy channels
    - Rate limiting and restart budgets
    - Startup grace period handling
    - Detailed health reporting
    """
    
    def __init__(
        self,
        config: Optional[HealthMonitorConfig] = None,
        health_check_fn: Optional[Callable[[str, Any], "Awaitable[HealthResult]"]] = None,
        restart_fn: Optional[Callable[[str, HealthReason], "Awaitable[None]"]] = None,
    ):
        """Initialize health monitor.
        
        Args:
            config: Monitor configuration
            health_check_fn: Function to get channel health (name, bot) -> HealthResult
            restart_fn: Function to restart a channel (name, reason) -> None
        """
        self._config = config or HealthMonitorConfig()
        self._health_check_fn = health_check_fn
        self._restart_fn = restart_fn
        self._channels: Dict[str, Any] = {}  # name -> bot
        self._restart_history: Dict[str, ChannelRestartHistory] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check_time: Dict[str, float] = {}
        self._suspended_channels: Set[str] = set()  # Channels to skip monitoring
    
    def register_channel(self, name: str, bot: Any) -> None:
        """Register a channel for health monitoring.
        
        Args:
            name: Channel name
            bot: Bot instance
        """
        self._channels[name] = bot
        if name not in self._restart_history:
            self._restart_history[name] = ChannelRestartHistory()
        logger.debug(f"Health monitor: registered channel '{name}'")
    
    def unregister_channel(self, name: str) -> None:
        """Unregister a channel from health monitoring.
        
        Args:
            name: Channel name
        """
        self._channels.pop(name, None)
        self._last_check_time.pop(name, None)
        self._suspended_channels.discard(name)
        logger.debug(f"Health monitor: unregistered channel '{name}'")
    
    def suspend_channel(self, name: str) -> None:
        """Temporarily suspend health monitoring for a channel.
        
        Useful during manual operations or known maintenance.
        
        Args:
            name: Channel name
        """
        self._suspended_channels.add(name)
        logger.info(f"Health monitor: suspended monitoring for channel '{name}'")
    
    def resume_channel(self, name: str) -> None:
        """Resume health monitoring for a suspended channel.
        
        Args:
            name: Channel name
        """
        self._suspended_channels.discard(name)
        logger.info(f"Health monitor: resumed monitoring for channel '{name}'")
    
    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            logger.warning("Health monitor already running")
            return
        
        if not self._config.enabled:
            logger.info("Health monitor disabled by configuration")
            return
        
        self._running = True
        self._task = asyncio.create_task(
            self._monitor_loop(),
            name="health-monitor",
        )
        logger.info(f"Health monitor started (interval={self._config.interval}s)")
    
    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        if not self._running:
            return
        
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Health monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all_channels()
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
            
            # Sleep with cancellation support
            try:
                await asyncio.sleep(self._config.interval)
            except asyncio.CancelledError:
                break
    
    async def _check_all_channels(self) -> None:
        """Check health of all registered channels."""
        current_time = time.time()
        
        for name, bot in list(self._channels.items()):
            # Skip suspended channels
            if name in self._suspended_channels:
                continue
            
            try:
                await self._check_channel(name, bot, current_time)
            except Exception as e:
                logger.warning(f"Health check failed for channel '{name}': {e}")
    
    async def _check_channel(self, name: str, bot: Any, current_time: float) -> None:
        """Check health of a single channel.
        
        Args:
            name: Channel name
            bot: Bot instance
            current_time: Current timestamp
        """
        # Get health status
        if self._health_check_fn:
            try:
                health = await self._health_check_fn(name, bot)
            except Exception as e:
                logger.warning(f"Failed to get health for channel '{name}': {e}")
                return
        else:
            # Try to call bot.health() directly if no custom function
            if hasattr(bot, "health"):
                try:
                    health = await bot.health()
                except Exception as e:
                    logger.warning(f"Failed to get health for channel '{name}': {e}")
                    return
            else:
                # No health check available
                return
        
        # Evaluate health
        reason = evaluate_channel_health(
            health,
            startup_grace_seconds=self._config.startup_grace,
            stale_after_seconds=self._config.stale_after,
            stuck_after_seconds=self._config.stuck_after,
            current_time=current_time,
        )
        
        # Record check time
        self._last_check_time[name] = current_time
        
        # Log health status
        if reason != HealthReason.HEALTHY:
            logger.info(f"Channel '{name}' health: {reason.value}")
        
        # Check if restart is needed and allowed
        if reason.is_recoverable:
            history = self._restart_history[name]
            
            # Check restart budget
            if not history.can_restart(self._config.max_restarts_per_hour, current_time):
                restart_count = history.get_restart_count(current_time)
                logger.warning(
                    f"Channel '{name}' needs restart (reason={reason.value}) "
                    f"but rate limit exceeded ({restart_count}/{self._config.max_restarts_per_hour} per hour)"
                )
                return
            
            # Trigger restart
            logger.info(f"Triggering restart for channel '{name}' (reason={reason.value})")
            history.record_restart(current_time)
            
            if self._restart_fn:
                try:
                    await self._restart_fn(name, reason)
                except Exception as e:
                    logger.error(f"Failed to restart channel '{name}': {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitor status.
        
        Returns:
            Dictionary with monitor status and channel information
        """
        current_time = time.time()
        
        channel_status = {}
        for name in self._channels:
            history = self._restart_history.get(name, ChannelRestartHistory())
            channel_status[name] = {
                "last_check": self._last_check_time.get(name),
                "suspended": name in self._suspended_channels,
                "restart_count": history.get_restart_count(current_time),
                "can_restart": history.can_restart(self._config.max_restarts_per_hour, current_time),
            }
        
        return {
            "enabled": self._config.enabled,
            "running": self._running,
            "interval": self._config.interval,
            "channels": channel_status,
        }