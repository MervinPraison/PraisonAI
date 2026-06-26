"""
BotOS — multi-platform bot orchestrator.

Manages multiple Bot instances across different messaging platforms
with a single unified lifecycle.

Hierarchy::

    BotOS  (multi-platform orchestrator)  ← this class
    └── Bot  (single platform)
        └── Agent / AgentTeam / AgentFlow  (AI brain)

Usage::

    from praisonai.bots import BotOS, Bot
    from praisonaiagents import Agent

    agent = Agent(name="assistant", instructions="Be helpful")

    # Approach 1: Explicit bots
    botos = BotOS(bots=[
        Bot("telegram", agent=agent),
        Bot("discord", agent=agent),
    ])
    await botos.start()

    # Approach 2: Shortcut — same agent, multiple platforms
    botos = BotOS(agent=agent, platforms=["telegram", "discord"])
    await botos.start()

    # Approach 3: Build incrementally
    botos = BotOS()
    botos.add_bot(Bot("telegram", agent=agent))
    botos.add_bot(Bot("slack", agent=agent, app_token="xapp-..."))
    await botos.start()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.bots.protocols import HealthReason, HealthResult, evaluate_channel_health
from ..gateway.supervisor import ChannelSupervisor
from ..gateway.health_monitor import ChannelHealthMonitor, HealthMonitorConfig
from .bot import Bot
from .delivery import DeliveryRouter, SessionSource

logger = logging.getLogger(__name__)


class BotOS:
    """Multi-platform bot orchestrator.

    Starts and stops all registered Bot instances concurrently.
    Satisfies ``BotOSProtocol`` from the core SDK.

    Args:
        bots: Pre-built Bot instances.
        agent: Shared agent for auto-created bots (used with *platforms*).
        platforms: List of platform names; creates a Bot per platform
            using the shared *agent*.
        config: Optional BotOSConfig.
    """

    def __init__(
        self,
        bots: Optional[List[Bot]] = None,
        agent: Optional[Any] = None,
        platforms: Optional[List[str]] = None,
        config: Optional[Any] = None,
        identity_resolver: Optional[Any] = None,
        health_monitor: Optional[HealthMonitorConfig] = None,
        enable_supervision: bool = True,
        idle_policy: Optional[Any] = None,
    ):
        self._bots: Dict[str, Bot] = {}
        self._is_running = False
        self._config = config
        # Issue #2332: opt-in idle-dormancy / scale-to-zero. Default off —
        # when None the gateway behaves exactly as before (always-on).
        self._idle_policy = idle_policy
        self._last_inbound_ts: float = time.time()
        self._running_turns: int = 0
        self._is_dormant: bool = False
        self._on_quiesce = None  # optional callable(): host-suspend driver
        # W1: shared identity resolver applied to every managed bot —
        # gives cross-platform unified-user sessions out of the box.
        self._identity_resolver = identity_resolver
        self._tasks: List[asyncio.Task] = []
        
        # Initialize delivery router for proactive outbound messaging
        self._delivery_router = DeliveryRouter(self)
        
        self._enable_supervision = enable_supervision
        
        # Initialize supervisor and health monitor if enabled
        if self._enable_supervision:
            self._supervisor = ChannelSupervisor(health_config=health_monitor)
            self._health_monitor_config = health_monitor or HealthMonitorConfig()
        else:
            self._supervisor = None
            self._health_monitor_config = None
        
        self._start_times: Dict[str, float] = {}  # Track bot start times

        # Register explicit bots
        if bots:
            for bot in bots:
                self.add_bot(bot)

        # Shortcut: agent + platforms → auto-create Bot per platform
        if agent and platforms:
            for plat in platforms:
                if plat not in self._bots:
                    self.add_bot(
                        Bot(
                            plat,
                            agent=agent,
                            identity_resolver=self._identity_resolver,
                        )
                    )

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ── Bot management ──────────────────────────────────────────────

    def add_bot(self, bot: Bot) -> None:
        """Register a Bot for orchestration.

        Args:
            bot: A Bot instance.
        """
        # W1: propagate the BotOS-level resolver to bots that don't
        # already have one, so cross-platform unification works whether
        # the user uses the shortcut API or constructs Bots manually.
        if (
            self._identity_resolver is not None
            and getattr(bot, "_identity_resolver", None) is None
        ):
            bot._identity_resolver = self._identity_resolver
        self._bots[bot.platform] = bot

    def list_bots(self) -> List[str]:
        """List platform names of all registered bots."""
        return list(self._bots.keys())

    def get_bot(self, platform: str) -> Optional[Bot]:
        """Get a registered bot by platform name."""
        return self._bots.get(platform.lower())

    def _get_hook_runner(self) -> Any:
        """Resolve a HookRunner from the first registered bot's agent.

        Returns None when no bot/agent exposes a hook runner — callers
        treat None as a no-op so there is zero overhead without hooks.
        """
        from ._protocol_mixin import _resolve_runner_from_agent

        for bot in self._bots.values():
            agent = bot.get_agent() if hasattr(bot, "get_agent") else getattr(bot, "_agent", None)
            runner = _resolve_runner_from_agent(agent)
            if runner is not None:
                return runner
        return None
    
    @property
    def delivery_router(self) -> DeliveryRouter:
        """Get the delivery router for proactive messaging."""
        return self._delivery_router

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start all registered bots concurrently.

        Each bot runs in its own asyncio task. BotOS waits for all
        bots (they block until stopped).
        """
        if self._is_running:
            logger.warning("BotOS already running")
            return

        if not self._bots:
            logger.warning("BotOS: no bots registered, nothing to start")
            return

        self._is_running = True
        logger.info(f"BotOS starting {len(self._bots)} bot(s): {', '.join(self._bots.keys())}")

        # Fire GATEWAY_START lifecycle hook (no-op when no hooks registered)
        try:
            from ._protocol_mixin import fire_gateway_start
            fire_gateway_start(self._get_hook_runner(), list(self._bots.keys()))
        except Exception as e:
            logger.debug(f"GATEWAY_START emit error (non-fatal): {e}")

        # Configure delivery router from bot configurations
        self._configure_delivery_from_bots()

        # Start health monitoring if enabled
        if self._enable_supervision and self._supervisor:
            await self._supervisor.start_health_monitoring()
            logger.info("BotOS: health monitoring enabled")

        self._tasks = []
        for platform, bot in self._bots.items():
            task = asyncio.create_task(
                self._run_bot(platform, bot),
                name=f"botos-{platform}",
            )
            self._tasks.append(task)

        # Start schedule loop alongside bots so cron jobs execute
        schedule_task = asyncio.create_task(
            self._run_schedule_loop(),
            name="botos-scheduler",
        )
        self._tasks.append(schedule_task)

        # Issue #2332: opt-in idle-dormancy loop. Only scheduled when an
        # idle_policy is configured, so always-on gateways pay zero cost.
        if self._idle_policy is not None:
            idle_task = asyncio.create_task(
                self._run_idle_loop(),
                name="botos-idle",
            )
            self._tasks.append(idle_task)

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            # Stop health monitoring
            if self._enable_supervision and self._supervisor:
                await self._supervisor.stop_health_monitoring()
            self._is_running = False

    async def _run_bot(self, platform: str, bot: Bot) -> None:
        """Run a single bot with error isolation and optional supervision."""
        if self._enable_supervision and self._supervisor:
            # Run with supervision and auto-recovery
            async def start_bot(name: str, bot_instance: Bot) -> None:
                self._start_times[name] = time.time()
                await bot_instance.start()
            
            await self._supervisor.run(platform, bot, start_bot)
        else:
            # Original behavior without supervision
            try:
                logger.info(f"BotOS: starting {platform}")
                self._start_times[platform] = time.time()
                await bot.start()
            except Exception as e:
                logger.error(f"BotOS: {platform} failed: {e}")

    # ── Idle-dormancy / scale-to-zero (Issue #2332) ─────────────────

    def notify_inbound(self) -> None:
        """Record an inbound message for idle tracking.

        Resets the process-wide idle timer. Safe to call always — it is a
        cheap timestamp write whether or not an idle policy is configured.

        Note: the idle loop also passively probes each bot's session
        manager (``_active_runs``/``_last_active``) via
        :meth:`_probe_activity`, so live traffic is reflected even without
        calling this — these hooks are an optional explicit override for
        adapters that don't expose a session manager. When no
        ``idle_policy`` is configured they are no-op-cheap and the gateway
        stays always-on as before.
        """
        self._last_inbound_ts = time.time()

    def turn_started(self) -> None:
        """Mark an agent turn as in-flight (blocks dormancy)."""
        self._running_turns += 1
        self._last_inbound_ts = time.time()

    def turn_finished(self) -> None:
        """Mark an agent turn as complete."""
        if self._running_turns > 0:
            self._running_turns -= 1

    def _probe_activity(self) -> tuple[int, float]:
        """Passively read live liveness facts from bot session managers.

        Closes the "stale counters" gap (#2332 reviewer P1): rather than
        relying solely on explicit :meth:`notify_inbound`/:meth:`turn_started`
        calls (which not every adapter wires), this reads the session
        manager state that *every* adapter already maintains:

        * ``_active_runs`` — in-flight agent turns per user, populated and
          popped around each agent run.
        * ``_last_active`` — per-user last-inbound timestamp (monotonic),
          stamped on every inbound message.

        Returns ``(running_turns, last_inbound_ts)`` where the timestamp is
        wall-clock (``time.time``) to match the policy contract. Explicitly
        recorded activity (``self._running_turns`` / ``self._last_inbound_ts``)
        is merged in, so adapters that do call the hooks still win and any
        adapter that exposes neither degrades to the construction-time value.
        """
        running = self._running_turns
        last_ts = self._last_inbound_ts
        now_wall = time.time()
        now_mono = time.monotonic()
        for bot in self._bots.values():
            session = getattr(bot, "_session", None)
            if session is None:
                adapter = getattr(bot, "_adapter", None)
                session = getattr(adapter, "_session", None)
            if session is None:
                continue
            active_runs = getattr(session, "_active_runs", None)
            if isinstance(active_runs, dict):
                running += len(active_runs)
            last_active = getattr(session, "_last_active", None)
            if isinstance(last_active, dict) and last_active:
                # Stored as monotonic; convert the most-recent to wall-clock.
                newest_mono = max(last_active.values())
                wall = now_wall - max(0.0, now_mono - newest_mono)
                if wall > last_ts:
                    last_ts = wall
        return running, last_ts

    def _has_background_work(self) -> bool:
        """Whether live background work should block dormancy.

        Conservative: any *enabled* scheduled job keeps the gateway awake.
        Checking only currently-due jobs is unsafe — a job scheduled to
        fire after the idle timeout would let the gateway quiesce first,
        and the schedule loop would later deliver its output through
        stopped transports, losing the result. While transports cannot be
        revived in-process, an enabled schedule means the gateway must
        stay resident to honour it (#2332 reviewer feedback).
        """
        try:
            from praisonaiagents.tools.schedule_tools import _get_store
            from praisonaiagents.scheduler import ScheduleRunner
        except ImportError:
            return False
        try:
            runner = ScheduleRunner(_get_store())
            if runner.get_due_jobs():
                return True
            store = _get_store()
            jobs = store.list() if hasattr(store, "list") else []
            return any(getattr(job, "enabled", False) for job in jobs)
        except Exception:
            return False

    async def wake(self) -> None:
        """Resume the gateway from dormancy and reconnect transports.

        Idempotent: a no-op when not dormant. Reuses ``HookAction.WAKE``
        semantics — an inbound poke revives the process and reconnects
        the messaging transports with session state preserved.
        """
        if not self._is_dormant:
            return
        logger.info("BotOS: waking from dormancy")
        self._is_dormant = False
        self.notify_inbound()
        # Prune finished task handles so repeated wake cycles don't
        # accumulate stale entries.
        self._tasks = [t for t in self._tasks if not t.done()]
        for platform, bot in self._bots.items():
            try:
                start = getattr(bot, "start", None)
                if start is not None:
                    task = asyncio.create_task(
                        self._run_bot(platform, bot),
                        name=f"botos-{platform}",
                    )
                    # Supervise: the main start() gather already returned the
                    # handles it had at launch, so wake-restarted tasks run
                    # outside it. Attach a callback to surface their failures.
                    task.add_done_callback(self._on_wake_task_done)
                    self._tasks.append(task)
            except Exception as e:
                logger.warning(f"BotOS: error waking {platform}: {e}")

    @staticmethod
    def _on_wake_task_done(task: "asyncio.Task") -> None:
        """Surface exceptions from wake-restarted transport tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"BotOS: wake task {task.get_name()} failed: {exc}")

    async def _quiesce(self, reason: str) -> None:
        """Stand transports down and signal the compute host to suspend."""
        if self._is_dormant:
            return
        logger.info(f"BotOS: quiescing (scale-to-zero): {reason}")
        self._is_dormant = True
        for platform, bot in self._bots.items():
            try:
                stop = getattr(bot, "stop", None)
                if stop is not None:
                    await bot.stop()
            except Exception as e:
                logger.warning(f"BotOS: error quiescing {platform}: {e}")
        # Drive the optional compute-host suspend (Fly/Modal/Daytona) only
        # after transports are cleanly down, so no inbound is dropped.
        if self._on_quiesce is not None:
            try:
                result = self._on_quiesce()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"BotOS: on_quiesce driver error: {e}")

    async def _run_idle_loop(self) -> None:
        """Evaluate the idle policy and quiesce when fully idle.

        Only scheduled when an ``idle_policy`` is configured. The policy
        decision is a pure, core-side predicate; this loop supplies live
        facts and owns the side effects.
        """
        policy = self._idle_policy
        wake_url = getattr(policy, "wake_url", None)
        # Arm gating: never quiesce into a state we cannot resume from.
        if hasattr(policy, "should_arm"):
            if not policy.should_arm(
                transports_quiescable=True,
                wake_registered=wake_url is not None,
            ):
                logger.info(
                    "BotOS: idle policy not armed (no wake path); staying always-on"
                )
                return
        logger.info("BotOS: idle-dormancy armed (scale-to-zero)")
        while self._is_running:
            await asyncio.sleep(30)
            if self._is_dormant:
                continue
            try:
                # Probe live liveness from session managers so the decision
                # reflects real traffic even when adapters don't call the
                # explicit notify_inbound/turn_* hooks (#2332 reviewer P1).
                running_turns, last_inbound_ts = self._probe_activity()
                decision = policy.is_idle(
                    running_turns=running_turns,
                    last_inbound_ts=last_inbound_ts,
                    has_background_work=self._has_background_work(),
                    now=time.time(),
                )
            except Exception as e:
                logger.debug(f"BotOS: idle evaluation error: {e}")
                continue
            if getattr(decision, "idle", False):
                await self._quiesce(getattr(decision, "reason", ""))

    async def _run_schedule_loop(self) -> None:
        """Poll for due scheduled jobs and execute them.

        Runs alongside bot tasks so cron/interval schedules fire even
        without the UI. On trigger, the agent processes the message
        and results are delivered back to the originating platform.

        When the UI scheduler is already running (PraisonAIUI started),
        this loop defers to it to avoid double-firing jobs.
        """
        try:
            from praisonaiagents.tools.schedule_tools import _get_store
            from praisonaiagents.scheduler import ScheduleRunner
        except ImportError:
            logger.debug("BotOS: schedule module not available, skipping scheduler")
            return

        store = _get_store()
        runner = ScheduleRunner(store)
        logger.info("BotOS: schedule loop started (30s tick)")

        while True:
            try:
                # Skip if the UI scheduler is already running (avoids double-fire)
                ui_running = False
                try:
                    from praisonaiui.features.schedules import _scheduler_running
                    ui_running = _scheduler_running
                except ImportError:
                    pass  # UI not installed — we're the only scheduler
                if ui_running:
                    await asyncio.sleep(30)
                    continue

                due = runner.get_due_jobs()
                for job in due:
                    import time as _time
                    _start = _time.time()
                    _status = "succeeded"
                    _result = None
                    _error = None
                    _delivered = False
                    try:
                        _result, _delivered = await self._execute_schedule_job(job)
                    except Exception as e:
                        _status = "failed"
                        _error = str(e)
                        logger.warning(f"BotOS: schedule job {job.name} failed: {e}")
                    _duration = _time.time() - _start
                    runner.mark_run(
                        job,
                        status=_status,
                        result=_result,
                        error=_error,
                        duration=_duration,
                        delivered=_delivered,
                    )
            except Exception as e:
                logger.debug(f"BotOS: schedule tick error: {e}")
            await asyncio.sleep(30)

    async def _execute_schedule_job(self, job) -> tuple:
        """Execute a single due schedule job.

        Returns:
            Tuple of (result_str, delivered_bool).
        """
        if not job.message:
            return (None, False)

        # Find the agent to execute with
        agent = None
        if job.agent_id:
            # Look for a bot whose agent matches
            for bot in self._bots.values():
                a = bot.get_agent() if hasattr(bot, 'get_agent') else getattr(bot, '_agent', None)
                if a and getattr(a, 'name', None) == job.agent_id:
                    agent = a
                    break
        if agent is None:
            # Use the first available agent
            for bot in self._bots.values():
                a = bot.get_agent() if hasattr(bot, 'get_agent') else getattr(bot, '_agent', None)
                if a:
                    agent = a
                    break
        if agent is None:
            logger.debug(f"BotOS: no agent for schedule job {job.name}")
            return (None, False)

        # Fire SCHEDULE_TRIGGER lifecycle hook (no-op when no hooks registered)
        try:
            from ._protocol_mixin import fire_schedule_trigger, _resolve_runner_from_agent
            fire_schedule_trigger(
                _resolve_runner_from_agent(agent),
                job_name=getattr(job, "name", ""),
                job_id=str(getattr(job, "id", "") or getattr(job, "agent_id", "") or ""),
                message=job.message,
            )
        except Exception as e:
            logger.debug(f"SCHEDULE_TRIGGER emit error (non-fatal): {e}")

        # Run the agent
        result = await asyncio.to_thread(agent.chat, job.message)
        result_str = str(result) if result else None

        # Deliver using the new delivery router
        delivered = False
        delivery = job.delivery
        if delivery:
            # Build origin context if available
            origin = None
            if delivery.channel and delivery.channel_id:
                origin = SessionSource(
                    platform=delivery.channel,
                    channel_id=delivery.channel_id
                )
            
            # Determine target - use explicit target if set, otherwise "origin"
            target = getattr(delivery, 'target', None)
            if not target and origin:
                target = "origin"
            
            if target and result_str:
                delivered = await self._delivery_router.deliver(
                    target=target,
                    text=result_str,
                    origin=origin
                )

        logger.info(f"BotOS: executed schedule job '{job.name}'")
        return (result_str, delivered)
    
    def _configure_delivery_from_bots(self) -> None:
        """Configure delivery router from bot configurations."""
        for platform, bot in self._bots.items():
            # Check if bot has channel configuration
            # Try _config first (for manually created bots), then _kwargs (from from_config())
            config = getattr(bot, '_config', None)
            kwargs = getattr(bot, '_kwargs', {})
            
            # Extract home_channel and aliases from config or kwargs
            home_channel = None
            aliases = {}
            
            if config:
                home_channel = getattr(config, 'home_channel', None)
                aliases = getattr(config, 'aliases', {})
            elif kwargs:
                home_channel = kwargs.get('home_channel')
                aliases = kwargs.get('aliases', {})
            
            # Set home channel if configured
            if home_channel:
                self._delivery_router.directory.set_home_channel(platform, home_channel)
            
            # Add aliases if configured
            for alias_name, channel_id in aliases.items():
                self._delivery_router.directory.add_alias(alias_name, platform, channel_id)
    
    def configure_channels(self, config: Dict[str, Any]) -> None:
        """
        Configure channel directory from a dictionary.
        
        Args:
            config: Dictionary with platform configurations
            
        Example::
            
            botos.configure_channels({
                "telegram": {
                    "home_channel": "123456",
                    "aliases": {
                        "ops-alerts": "123456",
                        "dev-chat": "789012"
                    }
                },
                "discord": {
                    "home_channel": "456789"
                }
            })
        """
        self._delivery_router.configure_from_dict(config)
    
    async def deliver(self, target: str, text: str, origin: Optional[SessionSource] = None) -> bool:
        """
        Deliver a message to a target channel.
        
        Args:
            target: Target specification (origin|platform|platform:channel|alias)
            text: Message content to deliver
            origin: Optional source of the original request
            
        Returns:
            True if delivered successfully, False otherwise
            
        Example::
            
            # Reply to origin
            await botos.deliver("origin", "Hello!", origin=source)
            
            # Send to specific platform's home channel
            await botos.deliver("telegram", "Alert!")
            
            # Send to specific channel
            await botos.deliver("telegram:123456", "Build complete")
            
            # Send to aliased channel
            await botos.deliver("ops-alerts", "Disk full")
        """
        return await self._delivery_router.deliver(target, text, origin)

    async def stop(self) -> None:
        """Gracefully stop all running bots."""
        if not self._is_running:
            return

        logger.info("BotOS stopping all bots...")

        # Fire GATEWAY_STOP lifecycle hook (no-op when no hooks registered)
        try:
            from ._protocol_mixin import fire_gateway_stop
            fire_gateway_stop(self._get_hook_runner(), list(self._bots.keys()))
        except Exception as e:
            logger.debug(f"GATEWAY_STOP emit error (non-fatal): {e}")

        # Stop health monitoring first
        if self._enable_supervision and self._supervisor:
            await self._supervisor.stop_health_monitoring()

        # Stop each bot
        for platform, bot in self._bots.items():
            try:
                await bot.stop()
                # Cleanup supervisor state
                if self._enable_supervision and self._supervisor:
                    self._supervisor.cleanup(platform)
            except Exception as e:
                logger.warning(f"BotOS: error stopping {platform}: {e}")

        # Cancel tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        self._is_running = False
        logger.info("BotOS stopped")

    def remove_bot(self, platform: str) -> bool:
        """Remove a registered bot by platform name.

        Args:
            platform: Platform identifier to remove.

        Returns:
            True if removed, False if not found.
        """
        key = platform.lower()
        if key in self._bots:
            del self._bots[key]
            return True
        return False

    def run(self) -> None:
        """Synchronous entry point — starts all bots.

        Convenience wrapper so users don't need ``asyncio.run()``.

        Usage::

            botos = BotOS(agent=agent, platforms=["telegram", "discord"])
            botos.run()  # blocks until Ctrl+C
        """
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logger.info("BotOS interrupted")

    @classmethod
    def from_config(cls, path: str) -> "BotOS":
        """Create a BotOS instance from a YAML config file.

        YAML format::

            name: My BotOS
            agent:
              name: assistant
              instructions: Be helpful
              llm: gpt-4o-mini
            platforms:
              telegram:
                token: ${TELEGRAM_BOT_TOKEN}
              discord:
                token: ${DISCORD_BOT_TOKEN}
            health:
              interval: 300
              startup_grace: 60
              max_restarts_per_hour: 10

        Args:
            path: Path to YAML config file.

        Returns:
            Configured BotOS instance.
        """
        import os
        import re

        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML required: pip install pyyaml")

        with open(path, "r") as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Invalid BotOS config: {path}")

        def _resolve_env(val):
            if isinstance(val, str):
                return re.sub(
                    r'\$\{([^}]+)\}',
                    lambda m: os.environ.get(m.group(1), m.group(0)),
                    val,
                )
            return val

        # Build agent from config
        agent = None
        agent_cfg = raw.get("agent")
        if agent_cfg and isinstance(agent_cfg, dict):
            from praisonaiagents import Agent

            # Core params always supported
            agent_kwargs: Dict[str, Any] = {
                "name": agent_cfg.get("name", "assistant"),
                "instructions": agent_cfg.get("instructions", "You are a helpful assistant."),
            }
            if agent_cfg.get("llm"):
                agent_kwargs["llm"] = agent_cfg["llm"]

            # Extended params — memory, tools, verbose, knowledge, guardrails
            if "memory" in agent_cfg:
                agent_kwargs["memory"] = agent_cfg["memory"]

            # Pass through known Agent params
            for key in ("role", "goal", "backstory", "planning", "reflection"):
                if key in agent_cfg:
                    agent_kwargs[key] = agent_cfg[key]

            # Resolve tool names to real functions
            tool_names = agent_cfg.get("tools")
            if tool_names and isinstance(tool_names, list):
                resolved_tools = []
                for tname in tool_names:
                    if isinstance(tname, str):
                        try:
                            import importlib
                            mod = importlib.import_module("praisonaiagents.tools")
                            fn = getattr(mod, tname, None)
                            if fn:
                                resolved_tools.append(fn)
                            else:
                                logger.warning(f"BotOS: tool '{tname}' not found in praisonaiagents.tools")
                        except ImportError:
                            logger.warning(f"BotOS: could not import tools module for '{tname}'")
                    else:
                        resolved_tools.append(tname)  # Already a callable
                if resolved_tools:
                    agent_kwargs["tools"] = resolved_tools

            if "knowledge" in agent_cfg:
                agent_kwargs["knowledge"] = agent_cfg["knowledge"]

            if "guardrail" in agent_cfg:
                agent_kwargs["guardrail"] = agent_cfg["guardrail"]

            agent = Agent(**agent_kwargs)

        # Build bots per platform
        bots = []
        platforms_cfg = raw.get("platforms", {})
        for plat_name, plat_cfg in platforms_cfg.items():
            if not isinstance(plat_cfg, dict):
                plat_cfg = {}
            # Resolve env vars in values
            resolved = {k: _resolve_env(v) for k, v in plat_cfg.items()}
            token = resolved.pop("token", None)
            bots.append(Bot(plat_name, agent=agent, token=token, **resolved))

        # Parse health configuration
        health_cfg = raw.get("health")
        health_monitor = None
        if health_cfg and isinstance(health_cfg, dict):
            health_monitor = HealthMonitorConfig.from_dict(health_cfg)

        # Check if supervision is disabled (handle null supervision key)
        supervision_cfg = raw.get("supervision") or {}
        enable_supervision = supervision_cfg.get("enabled", True)

        return cls(bots=bots, health_monitor=health_monitor, enable_supervision=enable_supervision)

    async def health(self) -> Dict[str, HealthResult]:
        """Get health status of all bots.
        
        Returns:
            Dictionary mapping platform name to HealthResult
        """
        results = {}
        current_time = time.time()
        
        for platform, bot in self._bots.items():
            try:
                if hasattr(bot, "health"):
                    results[platform] = await bot.health()
                else:
                    # Construct basic health result
                    uptime = None
                    if platform in self._start_times:
                        uptime = current_time - self._start_times[platform]
                    
                    results[platform] = HealthResult(
                        ok=bot.is_running if hasattr(bot, "is_running") else False,
                        platform=platform,
                        is_running=bot.is_running if hasattr(bot, "is_running") else False,
                        uptime_seconds=uptime,
                    )
            except Exception as e:
                results[platform] = HealthResult(
                    ok=False,
                    platform=platform,
                    is_running=False,
                    error=str(e),
                )
        
        return results
    
    def get_supervisor_status(self) -> Optional[Dict[str, Any]]:
        """Get supervisor status if enabled.
        
        Returns:
            Supervisor status dictionary or None if supervision disabled
        """
        if self._supervisor:
            return {
                "enabled": True,
                "channels": self._supervisor.get_all_status(),
                "health_monitor": self._supervisor.get_health_status(),
            }
        return {"enabled": False}
    
    def pause_bot(self, platform: str) -> bool:
        """Pause a bot (only works with supervision enabled).
        
        Args:
            platform: Platform name to pause
            
        Returns:
            True if paused, False otherwise
        """
        if self._supervisor:
            return self._supervisor.pause(platform)
        return False
    
    def resume_bot(self, platform: str) -> bool:
        """Resume a paused bot (only works with supervision enabled).
        
        Args:
            platform: Platform name to resume
            
        Returns:
            True if resumed, False otherwise
        """
        if self._supervisor:
            return self._supervisor.resume(platform)
        return False
    
    def reconnect_bot(self, platform: str) -> bool:
        """Force reconnect a bot (only works with supervision enabled).
        
        Args:
            platform: Platform name to reconnect
            
        Returns:
            True if reconnect triggered, False otherwise
        """
        if self._supervisor:
            return self._supervisor.reconnect(platform)
        return False
    
    def __repr__(self) -> str:
        platforms = list(self._bots.keys())
        supervised = "supervised" if self._enable_supervision else "unsupervised"
        return f"BotOS(platforms={platforms!r}, running={self._is_running}, mode={supervised})"
