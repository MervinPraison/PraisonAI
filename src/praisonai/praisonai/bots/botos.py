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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from .bot import Bot

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
    ):
        self._bots: Dict[str, Bot] = {}
        self._is_running = False
        self._config = config
        self._tasks: List[asyncio.Task] = []

        # Register explicit bots
        if bots:
            for bot in bots:
                self.add_bot(bot)

        # Shortcut: agent + platforms → auto-create Bot per platform
        if agent and platforms:
            for plat in platforms:
                if plat not in self._bots:
                    self.add_bot(Bot(plat, agent=agent))

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
        self._bots[bot.platform] = bot

    def list_bots(self) -> List[str]:
        """List platform names of all registered bots."""
        return list(self._bots.keys())

    def get_bot(self, platform: str) -> Optional[Bot]:
        """Get a registered bot by platform name."""
        return self._bots.get(platform.lower())

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

        self._tasks = []
        for platform, bot in self._bots.items():
            task = asyncio.create_task(
                self._run_bot(platform, bot),
                name=f"botos-{platform}",
            )
            self._tasks.append(task)

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self._is_running = False

    async def _run_bot(self, platform: str, bot: Bot) -> None:
        """Run a single bot with error isolation."""
        try:
            logger.info(f"BotOS: starting {platform}")
            await bot.start()
        except Exception as e:
            logger.error(f"BotOS: {platform} failed: {e}")

    async def stop(self) -> None:
        """Gracefully stop all running bots."""
        if not self._is_running:
            return

        logger.info("BotOS stopping all bots...")

        # Stop each bot
        for platform, bot in self._bots.items():
            try:
                await bot.stop()
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
            agent = Agent(
                name=agent_cfg.get("name", "assistant"),
                instructions=agent_cfg.get("instructions", "You are a helpful assistant."),
                llm=agent_cfg.get("llm"),
            )

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

        return cls(bots=bots)

    def __repr__(self) -> str:
        platforms = list(self._bots.keys())
        return f"BotOS(platforms={platforms!r}, running={self._is_running})"
