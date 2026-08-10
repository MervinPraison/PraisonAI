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
from praisonaiagents.gateway import FleetSupervisionPolicy

logger = logging.getLogger(__name__)

# Issue #3840: the single fleet-health fact recorded on the shared
# degraded-capability registry when the crash-loop breaker trips. One owner
# entry for the *whole* gateway, redacted and operator-actionable, so an
# operator never has to eyeball ten per-channel counters to see "the gateway is
# thrashing".
_FLEET_OWNER_KIND = "gateway"
_FLEET_OWNER_ID = "fleet"
_FLEET_RETRY_HINT = "praisonai gateway doctor"


@dataclass
class HealthMonitorConfig:
    """Configuration for channel health monitoring."""
    
    interval: float = 300.0  # 5 minutes default
    startup_grace: float = 60.0  # 1 minute grace period for startup
    stale_after: float = 120.0  # 2 minutes without inbound activity = stale
    stuck_after: float = 900.0  # 15 minutes busy with no progress = stuck
    max_restarts_per_hour: int = 10  # Rate limit for restarts (per-channel)
    enabled: bool = True  # Whether monitoring is enabled
    # Issue #3840: fleet-level crash-loop breaker thresholds. Sit on top of the
    # per-channel ``max_restarts_per_hour`` budget so a systemic fault (bad
    # shared provider, network partition, org-wide expired token) that restarts
    # every channel at once trips one aggregate breaker instead of each channel
    # independently burning its budget in a silent fleet-wide reconnect storm.
    fleet_restarts_per_hour: int = 40  # aggregate restart-rate breaker
    failing_channel_fraction: float = 0.5  # trip if >= this fraction failing
    breaker_cooldown_s: float = 120.0  # hold restarts this long once tripped
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthMonitorConfig":
        """Create config from dictionary.

        Numeric thresholds are parsed defensively: unresolved env placeholders
        (e.g. ``"${STUCK_AFTER}"``), empty strings, or non-numeric values fall
        back to the default instead of raising during config load, and values
        are clamped to a sane lower bound so a negative threshold can never
        cause healthy long-running turns to be restarted immediately.
        """
        defaults = cls()

        def _num(key: str, default: float, *, minimum: float, cast=float):
            raw = data.get(key, default)
            try:
                value = cast(raw)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid health config value for %r (%r); using default %r",
                    key, raw, default,
                )
                return default
            return max(value, minimum)

        return cls(
            interval=_num("interval", defaults.interval, minimum=1.0),
            startup_grace=_num("startup_grace", defaults.startup_grace, minimum=0.0),
            stale_after=_num("stale_after", defaults.stale_after, minimum=1.0),
            stuck_after=_num("stuck_after", defaults.stuck_after, minimum=1.0),
            max_restarts_per_hour=int(
                _num("max_restarts_per_hour", defaults.max_restarts_per_hour,
                     minimum=0, cast=int)
            ),
            enabled=bool(data.get("enabled", True)),
            fleet_restarts_per_hour=int(
                _num("fleet_restarts_per_hour", defaults.fleet_restarts_per_hour,
                     minimum=1, cast=int)
            ),
            failing_channel_fraction=min(
                _num("failing_channel_fraction",
                     defaults.failing_channel_fraction, minimum=0.01),
                1.0,
            ),
            breaker_cooldown_s=_num(
                "breaker_cooldown_s", defaults.breaker_cooldown_s, minimum=0.0
            ),
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
        degraded_registry: Optional[Any] = None,
    ):
        """Initialize health monitor.
        
        Args:
            config: Monitor configuration
            health_check_fn: Function to get channel health (name, bot) -> HealthResult
            restart_fn: Function to restart a channel (name, reason) -> None
            degraded_registry: Optional shared ``DegradedCapabilityRegistry`` so
                the fleet crash-loop breaker (Issue #3840) can record ONE
                ``gateway`` degraded-owner fact when it trips. ``None`` keeps the
                monitor fully functional (breaker still throttles) but silent on
                the aggregate degraded surface.
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
        # Issue #3840: fleet-level crash-loop breaker. A single aggregate view on
        # top of the per-channel restart budgets, so a systemic fault trips one
        # operator-visible breaker instead of every channel storming silently.
        self._degraded_registry = degraded_registry
        self._fleet_policy = FleetSupervisionPolicy(
            fleet_restarts_per_hour=self._config.fleet_restarts_per_hour,
            failing_channel_fraction=self._config.failing_channel_fraction,
            breaker_cooldown_s=self._config.breaker_cooldown_s,
        )
        self._fleet_tripped = False
    
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

        # Issue #3840: evaluate the aggregate failing-channel fraction every
        # sweep. A systemic fault can park every channel on its per-channel
        # budget WITHOUT producing new restarts, so the restart-rate signal
        # alone would never fire — this second signal trips the breaker when a
        # large fraction of the fleet is failing. Also re-evaluate the breaker
        # here (not only on a status read) so the degraded-owner fact clears on
        # the monitor loop once the storm subsides.
        if self._channels:
            failing = self._count_failing_channels(current_time)
            fraction_tripped = self._fleet_policy.note_fleet_state(
                failing, len(self._channels), current_time
            )
            if fraction_tripped and not self._fleet_tripped:
                self._trip_fleet_breaker("fleet", HealthReason.ERROR, current_time)

        if self._fleet_tripped and not self._fleet_policy.tripped(current_time):
            self._clear_fleet_breaker()
    
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

            # Issue #3840: fleet-level crash-loop breaker. The per-channel budget
            # passed, but if the *fleet* restart rate has crossed its threshold a
            # systemic fault is in progress — HOLD the restart, apply backpressure
            # and record ONE operator-visible degraded fact instead of feeding a
            # fleet-wide reconnect storm that risks an upstream rate-limit ban.
            if self._fleet_policy.note_restart(current_time):
                self._trip_fleet_breaker(name, reason, current_time)
                return

            # Trigger restart
            logger.info(f"Triggering restart for channel '{name}' (reason={reason.value})")
            history.record_restart(current_time)
            
            if self._restart_fn:
                try:
                    await self._restart_fn(name, reason)
                except Exception as e:
                    logger.error(f"Failed to restart channel '{name}': {e}")

    def _trip_fleet_breaker(
        self, channel: str, reason: HealthReason, current_time: float
    ) -> None:
        """Halt restarts and record ONE gateway degraded-owner fact (Issue #3840).

        Called when the fleet crash-loop breaker trips. Instead of restarting the
        offending channel (and every sibling behind it), the gateway backs off
        and surfaces a single, redacted, operator-actionable degraded state so
        ``gateway status`` / ``gateway doctor`` / ``/health`` show "the gateway is
        thrashing" with a next step — never inferred from ten per-channel counters.
        """
        total = len(self._channels)
        failing = self._count_failing_channels(current_time)
        logger.error(
            "Fleet crash-loop breaker TRIPPED: holding channel restarts "
            "(%d/%d channels failing, reason=%s). Backing off for %.0fs; "
            "run '%s' to diagnose.",
            failing, total, reason.value, self._config.breaker_cooldown_s,
            _FLEET_RETRY_HINT,
        )
        self._fleet_tripped = True
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            from praisonaiagents.gateway import DegradedOwner

            registry.mark(
                DegradedOwner(
                    owner_kind=_FLEET_OWNER_KIND,
                    owner_id=_FLEET_OWNER_ID,
                    state="stale",
                    reason=(
                        f"channel crash-loop: {failing}/{total} channels failing"
                        if total
                        else "channel crash-loop"
                    ),
                    retry_hint=_FLEET_RETRY_HINT,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to record fleet degraded-owner: %s", exc)

    def _clear_fleet_breaker(self) -> None:
        """Clear the fleet breaker + degraded-owner fact once the storm subsides."""
        if not self._fleet_tripped:
            return
        self._fleet_tripped = False
        self._fleet_policy.reset()
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            registry.clear(_FLEET_OWNER_KIND, _FLEET_OWNER_ID)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to clear fleet degraded-owner: %s", exc)

    def _count_failing_channels(self, current_time: float) -> int:
        """Count channels whose per-channel restart budget is currently exhausted.

        A proxy for "channels in a failing/parked state" that reuses the restart
        history already tracked per channel, so the fleet-fraction signal needs
        no extra bookkeeping.
        """
        budget = self._config.max_restarts_per_hour
        failing = 0
        for name in self._channels:
            history = self._restart_history.get(name)
            if history is None:
                continue
            # A disabled per-channel budget (``max_restarts_per_hour == 0``)
            # makes ``can_restart`` always False; an idle channel with no
            # recorded restarts is healthy, not failing, so only count channels
            # that have actually attempted restarts and exhausted their budget.
            if budget <= 0 and not history.timestamps:
                continue
            if not history.can_restart(budget, current_time):
                failing += 1
        return failing

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

        # Issue #3840: re-evaluate the breaker so a storm that has since gone
        # quiet clears its degraded-owner fact, and surface one fleet-health
        # signal alongside the per-channel counters.
        fleet_tripped = self._fleet_policy.tripped(current_time)
        if self._fleet_tripped and not fleet_tripped:
            self._clear_fleet_breaker()

        return {
            "enabled": self._config.enabled,
            "running": self._running,
            "interval": self._config.interval,
            "channels": channel_status,
            "fleet": {
                "breaker_tripped": self._fleet_tripped,
                "fleet_restarts_per_hour": self._config.fleet_restarts_per_hour,
                "failing_channels": self._count_failing_channels(current_time),
                "total_channels": len(self._channels),
            },
        }