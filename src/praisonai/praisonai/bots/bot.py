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

    def _build_adapter(self) -> Any:
        """Lazy-resolve and instantiate the platform adapter."""
        from ._registry import resolve_adapter

        adapter_cls = resolve_adapter(self._platform)

        # Build init kwargs for the adapter
        init_kwargs: Dict[str, Any] = {}
        init_kwargs["token"] = self.token

        if self._agent is not None:
            init_kwargs["agent"] = self._agent
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

    def __repr__(self) -> str:
        agent_name = getattr(self._agent, 'name', None) if self._agent else None
        return f"Bot(platform={self._platform!r}, agent={agent_name!r}, running={self.is_running})"
