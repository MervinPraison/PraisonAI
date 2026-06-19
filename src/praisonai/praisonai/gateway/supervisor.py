"""
Channel supervision for WebSocket Gateway.

Provides resilient channel management with error classification,
unlimited retries for recoverable errors, and operator controls.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from praisonaiagents.bots.protocols import HealthReason

from ..bots._resilience import (
    BackoffPolicy,
    ConnectionMonitor,
    is_recoverable_error,
    is_conflict_error,
    sleep_with_abort,
)
from .health_monitor import ChannelHealthMonitor, HealthMonitorConfig

logger = logging.getLogger(__name__)


class ChannelState(Enum):
    """Channel supervision states."""
    RUNNING = "running"
    FAILED = "failed"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class ChannelStatus:
    """Channel supervision status."""
    state: ChannelState = ChannelState.STOPPED
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    next_retry_at: Optional[float] = None
    total_recoveries: int = 0
    manual_pause: bool = False
    

class ChannelSupervisor:
    """Supervises channel lifecycle with resilient error handling.
    
    Provides:
    - Error classification (fatal vs recoverable)
    - Unlimited retries for recoverable errors with capped exponential backoff
    - Manual pause/resume/reconnect controls
    - Status tracking for health reporting
    """
    
    def __init__(
        self,
        policy: Optional[BackoffPolicy] = None,
        classify_fn: Optional[Callable[[BaseException, str], bool]] = None,
        health_config: Optional[HealthMonitorConfig] = None,
    ):
        """Initialize channel supervisor.
        
        Args:
            policy: Backoff policy for retries (uses default if None)
            classify_fn: Error classification function (uses is_recoverable_error if None)
            health_config: Health monitor configuration (uses defaults if None)
        """
        self._policy = policy or BackoffPolicy(max_attempts=0)  # Unlimited retries
        self._classify_fn = classify_fn or is_recoverable_error
        self._channels: Dict[str, ChannelStatus] = {}
        self._monitors: Dict[str, ConnectionMonitor] = {}
        self._abort_signals: Dict[str, asyncio.Event] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._bots: Dict[str, Any] = {}  # Store bot references for health checks
        
        # Initialize health monitor
        self._health_monitor = ChannelHealthMonitor(
            config=health_config,
            health_check_fn=self._get_channel_health,
            restart_fn=self._restart_channel_for_health,
        )
        
    def get_status(self, name: str) -> ChannelStatus:
        """Get current status of a channel."""
        return self._channels.get(name, ChannelStatus())
        
    def get_all_status(self) -> Dict[str, ChannelStatus]:
        """Get status of all supervised channels."""
        return dict(self._channels)
        
    def pause(self, name: str) -> bool:
        """Manually pause a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was running and paused, False otherwise
        """
        if name not in self._channels:
            return False
            
        status = self._channels[name]
        if status.state == ChannelState.RUNNING:
            status.state = ChannelState.PAUSED
            status.manual_pause = True
            
            # Signal abort to stop current operations
            if name in self._abort_signals:
                self._abort_signals[name].set()
                
            logger.info(f"Channel '{name}' manually paused")
            return True
            
        return False
        
    def resume(self, name: str) -> bool:
        """Resume a manually paused channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was paused and resumed, False otherwise
        """
        if name not in self._channels:
            return False
            
        status = self._channels[name]
        if status.state == ChannelState.PAUSED and status.manual_pause:
            status.state = ChannelState.STOPPED  # Will be restarted by supervision
            status.manual_pause = False
            
            # SET abort signal to wake the paused supervision loop
            if name in self._abort_signals:
                self._abort_signals[name].set()
                
            logger.info(f"Channel '{name}' manually resumed")
            return True
            
        return False
        
    def reconnect(self, name: str) -> bool:
        """Force reconnect of a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel exists, False otherwise
        """
        if name not in self._channels:
            return False
            
        # Reset monitor state and force restart
        if name in self._monitors:
            self._monitors[name].attempt = 0
            self._monitors[name].last_error = None
            self._monitors[name].last_error_time = None
            
        status = self._channels[name]
        status.state = ChannelState.STOPPED
        status.manual_pause = False  # Clear manual pause flag
        status.last_error = None
        status.last_error_time = None
        status.next_retry_at = None
        
        # Signal abort to stop current operations
        if name in self._abort_signals:
            self._abort_signals[name].set()
            
        logger.info(f"Channel '{name}' manually reconnected")
        return True
        
    async def run(self, name: str, bot: Any, start_fn: Callable[[str, Any], Any]) -> None:
        """Run a channel with supervision.
        
        Args:
            name: Channel name
            bot: Bot instance
            start_fn: Function to start the bot (should be async)
        """
        # Initialize supervision state
        if name not in self._channels:
            self._channels[name] = ChannelStatus()
        if name not in self._monitors:
            # Determine platform from bot for error classification
            platform = getattr(bot, 'platform', type(bot).__name__.lower())
            self._monitors[name] = ConnectionMonitor(platform=platform, policy=self._policy)
        if name not in self._abort_signals:
            self._abort_signals[name] = asyncio.Event()
        
        # Store bot reference and register with health monitor
        self._bots[name] = bot
        self._health_monitor.register_channel(name, bot)
            
        status = self._channels[name]
        monitor = self._monitors[name]
        abort_signal = self._abort_signals[name]
        
        logger.info(f"Starting supervision for channel '{name}'")
        
        while True:
            try:
                # Check if manually paused
                if status.manual_pause:
                    status.state = ChannelState.PAUSED
                    await abort_signal.wait()  # Wait until resumed
                    abort_signal.clear()
                    continue
                    
                # Check if task was cancelled
                if abort_signal.is_set():
                    abort_signal.clear()
                    
                status.state = ChannelState.RUNNING
                logger.info(f"Starting channel '{name}'..." + 
                           (f" (attempt {monitor.attempt + 1})" if monitor.attempt > 0 else ""))
                
                # Start the bot
                await start_fn(name, bot)
                
                # If we get here, the bot exited cleanly
                monitor.record_success()
                status.total_recoveries = monitor.total_recoveries  # Sync recovery count
                status.state = ChannelState.STOPPED
                logger.info(f"Channel '{name}' stopped cleanly")
                break
                
            except asyncio.CancelledError:
                logger.info(f"Channel '{name}' supervision cancelled")
                status.state = ChannelState.STOPPED
                break
                
            except Exception as e:
                # Classify the error
                is_recoverable = self._classify_fn(e, monitor.platform)
                is_conflict = is_conflict_error(e)
                
                if is_conflict:
                    # Conflict errors are fatal - another bot instance using same token
                    status.state = ChannelState.FAILED
                    status.last_error = f"Conflict error (fatal): {str(e)}"
                    status.last_error_time = time.time()
                    status.next_retry_at = None
                    logger.error(f"Channel '{name}' failed with conflict error: {e}")
                    break
                    
                elif not is_recoverable:
                    # Non-recoverable error - treat as fatal
                    status.state = ChannelState.FAILED  
                    status.last_error = f"Fatal error: {str(e)}"
                    status.last_error_time = time.time()
                    status.next_retry_at = None
                    logger.error(f"Channel '{name}' failed with fatal error: {e}")
                    break
                    
                else:
                    # Recoverable error - retry with backoff
                    delay = monitor.record_error(e)
                    status.last_error = str(e)
                    status.last_error_time = time.time()
                    status.next_retry_at = time.time() + delay
                    
                    logger.warning(f"Channel '{name}' error (recoverable): {e}")
                    logger.info(f"Retrying channel '{name}' in {delay:.1f}s...")
                    
                    # Sleep with abort signal support
                    completed = await sleep_with_abort(delay, abort_signal)
                    if not completed:
                        # Aborted - check if paused or reconnect requested
                        continue
        
        # Cleanup - don't overwrite terminal failure states
        if status.state != ChannelState.FAILED:
            status.state = ChannelState.STOPPED
        logger.info(f"Supervision ended for channel '{name}'")
        
    def cleanup(self, name: str) -> None:
        """Clean up supervision state for a channel."""
        self._channels.pop(name, None)
        self._monitors.pop(name, None)
        self._bots.pop(name, None)
        if name in self._abort_signals:
            self._abort_signals[name].set()
            self._abort_signals.pop(name, None)
        if name in self._tasks:
            task = self._tasks.pop(name)
            if not task.done():
                task.cancel()
        # Unregister from health monitor
        self._health_monitor.unregister_channel(name)
    
    async def _get_channel_health(self, name: str, bot: Any) -> Any:
        """Get health status for a channel.
        
        Used by the health monitor to check channel health.
        
        Args:
            name: Channel name
            bot: Bot instance
            
        Returns:
            HealthResult if available
        """
        if hasattr(bot, "health"):
            return await bot.health()
        # Fallback: construct basic health result
        from praisonaiagents.bots.protocols import HealthResult
        status = self.get_status(name)
        return HealthResult(
            ok=status.state == ChannelState.RUNNING,
            platform=getattr(bot, "platform", name),
            is_running=status.state == ChannelState.RUNNING,
            error=status.last_error,
        )
    
    async def _restart_channel_for_health(self, name: str, reason: HealthReason) -> None:
        """Restart a channel based on health check.
        
        Used by the health monitor to trigger restarts.
        
        Args:
            name: Channel name
            reason: Health reason for restart
        """
        logger.info(f"Health monitor requesting restart of '{name}' (reason={reason.value})")
        
        # Update status with health reason
        if name in self._channels:
            self._channels[name].last_error = f"Health check failed: {reason.value}"
            self._channels[name].last_error_time = time.time()
        
        # Trigger restart via reconnect
        self.reconnect(name)
    
    async def start_health_monitoring(self) -> None:
        """Start the health monitor."""
        await self._health_monitor.start()
    
    async def stop_health_monitoring(self) -> None:
        """Stop the health monitor."""
        await self._health_monitor.stop()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health monitor status."""
        return self._health_monitor.get_status()