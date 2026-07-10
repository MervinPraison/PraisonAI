"""
Bot — single-platform, agent-centric bot wrapper.

Provides a user-friendly API that delegates to platform-specific adapters
(TelegramBot, DiscordBot, SlackBot, WhatsAppBot).

Hierarchy::

    BotOS  (multi-platform orchestrator)
    └── Bot  (single platform)  ← this class
        └── Agent / AgentTeam / AgentFlow  (AI brain)

Usage::

    from praisonai_bot.bots import Bot
    from praisonaiagents import Agent

    agent = Agent(name="assistant", instructions="Be helpful")

    # Minimal — token from env (TELEGRAM_BOT_TOKEN)
    bot = Bot("telegram", agent=agent)
    await bot.start()

    # Explicit token
    bot = Bot("discord", agent=agent, token="YOUR_TOKEN")

    # Platform-specific kwargs
    bot = Bot("whatsapp", agent=agent, mode="web")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent

logger = logging.getLogger(__name__)

# Env-var convention: {PLATFORM}_BOT_TOKEN
_TOKEN_ENV_MAP = {
    "telegram": "TELEGRAM_BOT_TOKEN",
    "discord": "DISCORD_BOT_TOKEN",
    "slack": "SLACK_BOT_TOKEN",
    "whatsapp": "WHATSAPP_ACCESS_TOKEN",
    "linear": "LINEAR_OAUTH_TOKEN",
    "email": "EMAIL_APP_PASSWORD",
    "agentmail": "AGENTMAIL_API_KEY",
}

# Platform-specific extra env vars
_EXTRA_ENV_MAP = {
    "slack": {"app_token": "SLACK_APP_TOKEN"},
    "whatsapp": {"phone_number_id": "WHATSAPP_PHONE_NUMBER_ID"},
    "linear": {"signing_secret": "LINEAR_WEBHOOK_SECRET"},
    "email": {
        "email_address": "EMAIL_ADDRESS",
        "imap_server": "EMAIL_IMAP_SERVER",
        "smtp_server": "EMAIL_SMTP_SERVER",
    },
    "agentmail": {
        "inbox_id": "AGENTMAIL_INBOX_ID",
        "domain": "AGENTMAIL_DOMAIN",
    },
}


class Bot:
    """Single-platform bot wrapper — the user-facing API.

    Resolves the correct platform adapter at ``start()`` time (lazy),
    so no heavy imports happen at construction.

    Args:
        platform: Platform name ("telegram", "discord", "slack", "whatsapp").
        agent: Agent, AgentTeam, or AgentFlow to power the bot.
        token: Explicit token. Falls back to env var ``{PLATFORM}_BOT_TOKEN``.
        config: Optional BotConfig override.
        transport: Optional out-of-process relay transport (Issue #2485). When
            provided, the platform connection is owned by a separate connector
            process and relayed in, so the gateway needs no public inbound port
            and no platform SDK. Must satisfy
            ``praisonaiagents.gateway.RelayTransport``.
        enable_supervision: When True (default), the ``start()``/``run()`` path
            wraps the adapter's inbound run loop with a ``ChannelSupervisor``
            (auto-reconnect with capped exponential backoff + health-based
            restart) — the same resilience ``BotOS``/gateway already provides —
            so a single ``Bot("slack", ...).run()`` survives a dropped
            connection identically to Telegram. Set False to run the raw adapter
            without supervision (useful for tests or embedding).
        **kwargs: Platform-specific arguments passed to the adapter.
    """

    def __init__(
        self,
        platform: str,
        agent: Optional[Any] = None,
        token: Optional[str] = None,
        config: Optional[Any] = None,
        identity_resolver: Optional[Any] = None,
        transport: Optional[Any] = None,
        enable_supervision: bool = True,
        **kwargs: Any,
    ):
        self._platform = platform.lower().strip()
        self._agent = agent
        self._explicit_token = token
        self._config = config
        # Issue #2485: optional out-of-process relay transport. When provided,
        # the platform connection lives in a separate connector process and is
        # relayed in; the gateway needs no public inbound port and no platform
        # SDK. Must satisfy ``praisonaiagents.gateway.RelayTransport``. The
        # adapter build path short-circuits to a ``RelayAdapter`` in this case.
        self._transport = transport
        # W1: optional cross-platform identity resolver. Applied to the
        # adapter's ``_session`` after construction (duck-typed; works
        # with any adapter that exposes a BotSessionManager-compatible
        # ``_session`` attribute).
        self._identity_resolver = identity_resolver
        self._kwargs = kwargs

        # Issue #2372: optional delivery router, set by the owning BotOS so the
        # adapter's ``_session`` can register a concrete ``BotOutboundMessenger``
        # per turn, making the built-in core ``send_message`` tool deliver.
        # Spliced into the adapter session in ``_build_adapter`` (same duck-typed
        # post-construction pattern as ``identity_resolver``).
        self._delivery_router: Optional[Any] = None

        # Issue #2454: optional gateway-wide inbound admission gate, set by the
        # owning BotOS so the adapter's ``_session`` enforces the concurrency
        # ceiling / fair wait queue / overflow policy on the run-dispatch path.
        # Spliced into the adapter session in ``_build_adapter`` (same duck-typed
        # post-construction pattern as the delivery router).
        self._admission_gate: Optional[Any] = None

        # Issue #2869: supervise the single-Bot inbound run loop by default so
        # every channel (not just Telegram) auto-reconnects with capped backoff
        # and health-based restart, matching BotOS/gateway robustness.
        self._enable_supervision = enable_supervision
        self._supervisor: Optional[Any] = None
        self._supervisor_task: Optional[Any] = None

        self._adapter: Optional[Any] = None
        self._is_running = False

    # ── Properties ──────────────────────────────────────────────────

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def agent(self) -> Optional[Any]:
        return self._agent

    @agent.setter
    def agent(self, value: Any) -> None:
        self._agent = value
        if self._adapter and hasattr(self._adapter, 'set_agent'):
            self._adapter.set_agent(value)

    @property
    def token(self) -> str:
        """Resolve token: explicit > env var > empty."""
        if self._explicit_token:
            return self._explicit_token
        env_key = _TOKEN_ENV_MAP.get(self._platform, f"{self._platform.upper()}_BOT_TOKEN")
        return os.environ.get(env_key, "")

    @property
    def is_running(self) -> bool:
        if self._adapter and hasattr(self._adapter, 'is_running'):
            return self._adapter.is_running
        return self._is_running

    @property
    def adapter(self) -> Optional[Any]:
        """The underlying platform adapter (available after start)."""
        return self._adapter

    # ── Lifecycle ───────────────────────────────────────────────────

    def _apply_smart_defaults(self, agent: Any, session_key: str = None) -> Any:
        """Enhance agent with sensible bot defaults if not already configured.
        
        DEPRECATED: Use apply_bot_smart_defaults from ._defaults module directly.
        This method is kept for backward compatibility.
        """
        from ._defaults import apply_bot_smart_defaults
        # Generate session key if not provided
        if session_key is None:
            import uuid
            session_key = str(uuid.uuid4())[:8]
        return apply_bot_smart_defaults(agent, self._config, session_key=session_key)

    def _build_adapter(self) -> Any:
        """Lazy-resolve and instantiate the platform adapter."""
        import uuid

        # Issue #2485: when a relay transport is supplied, the platform
        # connection lives out-of-process. Wrap it in a RelayAdapter that
        # presents the same adapter contract (start/stop/send_message) so the
        # rest of the gateway is unchanged.
        if self._transport is not None:
            from ._relay_adapter import RelayAdapter

            session_key = f"{self._platform}-{str(uuid.uuid4())[:8]}"
            agent = self._apply_smart_defaults(
                self._agent, session_key=session_key
            )
            return RelayAdapter(
                transport=self._transport,
                platform=self._platform,
                agent=agent,
                config=self._config,
            )

        from ._registry import resolve_adapter

        adapter_cls = resolve_adapter(self._platform)

        # Apply smart defaults to agent before passing to adapter
        # Generate a session key for workspace isolation
        session_key = f"{self._platform}-{str(uuid.uuid4())[:8]}"
        agent = self._apply_smart_defaults(self._agent, session_key=session_key)

        # Build init kwargs for the adapter
        init_kwargs: Dict[str, Any] = {}
        init_kwargs["token"] = self.token

        if agent is not None:
            init_kwargs["agent"] = agent
        if self._config is not None:
            init_kwargs["config"] = self._config

        # Resolve extra env vars (e.g. SLACK_APP_TOKEN)
        extras = _EXTRA_ENV_MAP.get(self._platform, {})
        for param, env_key in extras.items():
            if param not in self._kwargs:
                env_val = os.environ.get(env_key, "")
                if env_val:
                    init_kwargs[param] = env_val

        # Merge user kwargs (override defaults)
        init_kwargs.update(self._kwargs)

        adapter = adapter_cls(**init_kwargs)

        # W1: post-construction wire-up for the identity resolver.
        # Adapters create their own BotSessionManager during __init__;
        # we splice the resolver in here so existing adapters need no
        # signature change.
        if self._identity_resolver is not None:
            session = getattr(adapter, "_session", None)
            if session is not None and hasattr(session, "_identity_resolver"):
                session._identity_resolver = self._identity_resolver
            else:
                logger.warning(
                    "Bot(%s): adapter has no BotSessionManager-compatible "
                    "_session; identity_resolver ignored.",
                    self._platform,
                )

        # Issue #2372: splice the delivery router into the adapter's session so
        # each agent turn can register a concrete ``BotOutboundMessenger`` for
        # the built-in ``send_message`` tool. Same duck-typed post-construction
        # wire-up as the identity resolver above; adapters expose the session
        # under ``_session`` or ``_session_mgr``.
        if self._delivery_router is not None:
            session = getattr(adapter, "_session", None) or getattr(
                adapter, "_session_mgr", None
            )
            if session is not None and hasattr(session, "_delivery_router"):
                session._delivery_router = self._delivery_router

        # Issue #2454: splice the gateway-wide admission gate into the adapter's
        # session so inbound runs are admitted through the global concurrency
        # ceiling / fair queue. Same duck-typed post-construction wire-up.
        if self._admission_gate is not None:
            session = getattr(adapter, "_session", None) or getattr(
                adapter, "_session_mgr", None
            )
            if session is not None and hasattr(session, "_admission_gate"):
                session._admission_gate = self._admission_gate

        return adapter

    def _supervision_enabled(self) -> bool:
        """Whether inbound supervision should wrap the adapter run loop.

        Honours the ``enable_supervision`` kwarg and lets an adapter opt out
        via ``supervised_inbound = False`` (e.g. relay/webhook adapters that
        own their own reconnect/dormancy). Falls back to raw start if the
        supervision layer cannot be imported (optional wrapper machinery).
        """
        if not self._enable_supervision:
            return False
        adapter = self._adapter
        if adapter is not None and getattr(adapter, "supervised_inbound", True) is False:
            return False
        return True

    @staticmethod
    async def _wait_until_stopped(adapter: Any) -> None:
        """Block until a non-blocking adapter's inbound source stops running.

        Adapters whose ``start()`` spawns a background task/server and returns
        immediately (Email poll, Linear/WhatsApp/AgentMail webhook servers) need
        the supervised run to stay alive so a drop is noticed and reconnected.
        Prefers awaiting the adapter's own background task when it exposes one
        (surfacing its exception so the supervisor can classify + reconnect),
        else falls back to polling the ``is_running`` flag.
        """
        import asyncio

        for attr in ("_poll_task", "_run_task", "_serve_task"):
            task = getattr(adapter, attr, None)
            if task is not None and hasattr(task, "__await__"):
                await task
                return
        while getattr(adapter, "is_running", False):
            await asyncio.sleep(0.5)

    async def start(self) -> None:
        """Build the adapter and start the bot.

        By default (``enable_supervision=True``) the adapter's inbound run loop
        is wrapped in a :class:`ChannelSupervisor` so a dropped connection is
        reconnected with capped exponential backoff and an unhealthy channel is
        restarted — the same resilience ``BotOS``/gateway already provide, now
        on the single-``Bot`` path for *every* platform, not just Telegram
        (Issue #2869).
        """
        if self._adapter and self.is_running:
            logger.warning(f"Bot({self._platform}) already running")
            return

        self._adapter = self._build_adapter()
        self._is_running = True

        if not self._supervision_enabled():
            await self._adapter.start()
            return

        try:
            from ..gateway.supervisor import ChannelSupervisor
        except Exception as exc:  # pragma: no cover - optional supervision layer
            logger.debug(
                "Bot(%s): supervision layer unavailable (%s); "
                "running adapter without supervision.",
                self._platform,
                exc,
            )
            await self._adapter.start()
            return

        self._supervisor = ChannelSupervisor()

        import asyncio

        async def _start(name: str, adapter: Any) -> None:
            # The supervisor's run loop treats the return of this coroutine as
            # "channel stopped cleanly" and stops supervising. Blocking adapters
            # (e.g. Slack ``handler.start_async()``, Discord ``client.start()``)
            # naturally hold here until disconnected. But several adapters spawn
            # their inbound source in a background task / server and return from
            # ``start()`` immediately (e.g. Email IMAP poll, Linear/WhatsApp/
            # AgentMail webhook servers). For those, returning would end
            # supervision the instant the bot came up — the inbound loop would
            # run unsupervised and ``Bot.run()`` would exit right after starting
            # (Issue #2869). So after ``start()`` returns we keep the supervised
            # run alive until the adapter reports it is no longer running,
            # surfacing an unexpected stop so the supervisor can reconnect.
            await adapter.start()
            if getattr(adapter, "is_running", False):
                await self._wait_until_stopped(adapter)

        await self._supervisor.start_health_monitoring()
        self._supervisor_task = asyncio.ensure_future(
            self._supervisor.run(self._platform, self._adapter, _start)
        )
        try:
            await self._supervisor_task
        except asyncio.CancelledError:
            pass
        finally:
            await self._supervisor.stop_health_monitoring()
            self._supervisor.cleanup(self._platform)
            self._supervisor_task = None

    async def stop(self) -> None:
        """Stop the bot."""
        # Tell the adapter to unblock its inbound loop first so the supervised
        # run returns cleanly, then cancel the supervision loop if still live.
        if self._adapter:
            await self._adapter.stop()
        task = getattr(self, "_supervisor_task", None)
        if task is not None and not task.done():
            task.cancel()
        elif self._supervisor is not None:
            try:
                self._supervisor.cleanup(self._platform)
            except Exception:
                pass
        self._is_running = False

    async def go_dormant(self) -> None:
        """Pause inbound dispatch while keeping the connection alive.

        Issue #2485: forwards to a relay adapter's ``go_dormant`` so a
        scale-to-zero controller can ask an out-of-process connector to keep
        buffering inbound events while the gateway sleeps, rather than
        disconnecting. A no-op for adapters that do not support dormancy.
        """
        adapter = self._adapter
        go_dormant = getattr(adapter, "go_dormant", None) if adapter else None
        if go_dormant is not None:
            await go_dormant()

    def run(self) -> None:
        """Synchronous entry point — starts the bot.

        Convenience wrapper so users don't need ``asyncio.run()``.

        Usage::

            bot = Bot("telegram", agent=agent)
            bot.run()  # blocks until Ctrl+C
        """
        import asyncio
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    # ── Delegation to adapter ──────────────────────────────────────

    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Any:
        """Send a message via the underlying adapter."""
        if not self._adapter:
            raise RuntimeError("Bot not started")
        return await self._adapter.send_message(
            channel_id, content, reply_to=reply_to, thread_id=thread_id
        )

    def on_message(self, handler: Callable) -> Callable:
        """Register a message handler (pre-start decorator)."""
        if self._adapter:
            return self._adapter.on_message(handler)
        # Store for later registration
        if not hasattr(self, '_pending_message_handlers'):
            self._pending_message_handlers: List[Callable] = []
        self._pending_message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler."""
        if self._adapter:
            return self._adapter.on_command(command)

        def decorator(func: Callable) -> Callable:
            if not hasattr(self, '_pending_command_handlers'):
                self._pending_command_handlers: Dict[str, Callable] = {}
            self._pending_command_handlers[command] = func
            return func
        return decorator

    async def probe(self) -> Any:
        """Test channel connectivity (builds adapter lazily if needed)."""
        if not self._adapter:
            self._adapter = self._build_adapter()
        if hasattr(self._adapter, 'probe'):
            return await self._adapter.probe()
        from praisonaiagents.bots import ProbeResult
        return ProbeResult(ok=False, platform=self._platform, error="Adapter does not support probe()")

    async def health(self) -> Any:
        """Get detailed health status."""
        if not self._adapter:
            self._adapter = self._build_adapter()
        if hasattr(self._adapter, 'health'):
            return await self._adapter.health()
        from praisonaiagents.bots import HealthResult
        return HealthResult(ok=False, platform=self._platform, error="Adapter does not support health()")

    def __repr__(self) -> str:
        agent_name = getattr(self._agent, 'name', None) if self._agent else None
        return f"Bot(platform={self._platform!r}, agent={agent_name!r}, running={self.is_running})"
