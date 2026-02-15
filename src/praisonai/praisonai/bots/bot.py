"""
Bot — single-platform, agent-centric bot wrapper.

Provides a user-friendly API that delegates to platform-specific adapters
(TelegramBot, DiscordBot, SlackBot, WhatsAppBot).

Hierarchy::

    BotOS  (multi-platform orchestrator)
    └── Bot  (single platform)  ← this class
        └── Agent / AgentTeam / AgentFlow  (AI brain)

Usage::

    from praisonai.bots import Bot
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
}

# Slack also needs an app token
_EXTRA_ENV_MAP = {
    "slack": {"app_token": "SLACK_APP_TOKEN"},
    "whatsapp": {"phone_number_id": "WHATSAPP_PHONE_NUMBER_ID"},
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
        **kwargs: Platform-specific arguments passed to the adapter.
    """

    def __init__(
        self,
        platform: str,
        agent: Optional[Any] = None,
        token: Optional[str] = None,
        config: Optional[Any] = None,
        **kwargs: Any,
    ):
        self._platform = platform.lower().strip()
        self._agent = agent
        self._explicit_token = token
        self._config = config
        self._kwargs = kwargs

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

    def _apply_smart_defaults(self, agent: Any) -> Any:
        """Enhance agent with sensible bot defaults if not already configured.
        
        Smart defaults are applied automatically:
        - Safe tools (search_web, schedule_add/list/remove) if agent has no tools
        - Memory enabled if not already set
        
        These defaults make Bot() immediately useful without extra configuration.
        Users who want full control can pre-configure their agent.
        """
        if agent is None:
            return agent
        
        # Only enhance Agent instances (not AgentTeam/AgentFlow)
        agent_cls_name = type(agent).__name__
        if agent_cls_name not in ("Agent",):
            return agent
        
        # Wire BotConfig.auto_approve_tools → Agent(approval=True)
        if self._config and getattr(self._config, 'auto_approve_tools', False):
            if getattr(agent, '_approval_backend', None) is None:
                from praisonaiagents.approval.backends import AutoApproveBackend
                agent._approval_backend = AutoApproveBackend()
                logger.debug(f"Bot: auto_approve_tools enabled for agent '{getattr(agent, 'name', '?')}'")
        
        # Wire BotConfig.autonomy → Agent autonomy (if not already enabled)
        autonomy_val = None
        if self._config:
            autonomy_val = getattr(self._config, 'autonomy', None)
        if autonomy_val and not getattr(agent, 'autonomy_enabled', False):
            agent._init_autonomy(autonomy_val)
            logger.debug(f"Bot: autonomy enabled for agent '{getattr(agent, 'name', '?')}'")
        
        # Inject session history if agent has no memory configured (zero-dep).
        # NOTE: No session_id here — BotSessionManager handles per-user
        # isolation by swapping chat_history before/after each agent.chat().
        current_memory = getattr(agent, 'memory', None)
        if current_memory is None:
            agent.memory = {
                "history": True,
                "history_limit": 20,
            }
            logger.debug(f"Bot: injected session history for agent '{getattr(agent, 'name', '?')}'")
        
        # Add default tools if agent has none
        current_tools = getattr(agent, 'tools', None) or []
        if not current_tools:
            try:
                from praisonaiagents.tools import (
                    schedule_add, schedule_list, schedule_remove,
                )
                default_tools = [schedule_add, schedule_list, schedule_remove]
                
                # Try to add search_web if available
                try:
                    from praisonaiagents.tools import search_web
                    default_tools.insert(0, search_web)
                except (ImportError, AttributeError):
                    pass
                
                agent.tools = default_tools
                logger.debug(f"Bot: applied default tools to agent '{getattr(agent, 'name', '?')}'")
            except ImportError:
                pass  # Tools not available, skip
        
        return agent

    def _build_adapter(self) -> Any:
        """Lazy-resolve and instantiate the platform adapter."""
        from ._registry import resolve_adapter

        adapter_cls = resolve_adapter(self._platform)

        # Apply smart defaults to agent before passing to adapter
        agent = self._apply_smart_defaults(self._agent)

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

        return adapter_cls(**init_kwargs)

    async def start(self) -> None:
        """Build the adapter and start the bot."""
        if self._adapter and self.is_running:
            logger.warning(f"Bot({self._platform}) already running")
            return

        self._adapter = self._build_adapter()
        self._is_running = True
        await self._adapter.start()

    async def stop(self) -> None:
        """Stop the bot."""
        if self._adapter:
            await self._adapter.stop()
        self._is_running = False

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
