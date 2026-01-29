"""
Bot CLI commands for PraisonAI.

Provides CLI commands for managing messaging bots.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class BotHandler:
    """Handler for bot CLI commands."""
    
    def start_telegram(
        self,
        token: Optional[str] = None,
        agent_file: Optional[str] = None,
    ) -> None:
        """Start a Telegram bot.
        
        Args:
            token: Telegram bot token (or use TELEGRAM_BOT_TOKEN env var)
            agent_file: Optional path to agent configuration file
        """
        token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            print("Error: Telegram bot token required")
            print("Provide via --token or TELEGRAM_BOT_TOKEN environment variable")
            return
        
        try:
            from praisonai.bots import TelegramBot
        except ImportError as e:
            print(f"Error: TelegramBot requires python-telegram-bot. {e}")
            print("Install with: pip install python-telegram-bot")
            return
        
        agent = self._load_agent(agent_file)
        bot = TelegramBot(token=token, agent=agent)
        
        print("Starting Telegram bot...")
        print("Press Ctrl+C to stop")
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def start_discord(
        self,
        token: Optional[str] = None,
        agent_file: Optional[str] = None,
    ) -> None:
        """Start a Discord bot.
        
        Args:
            token: Discord bot token (or use DISCORD_BOT_TOKEN env var)
            agent_file: Optional path to agent configuration file
        """
        token = token or os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            print("Error: Discord bot token required")
            print("Provide via --token or DISCORD_BOT_TOKEN environment variable")
            return
        
        try:
            from praisonai.bots import DiscordBot
        except ImportError as e:
            print(f"Error: DiscordBot requires discord.py. {e}")
            print("Install with: pip install discord.py")
            return
        
        agent = self._load_agent(agent_file)
        bot = DiscordBot(token=token, agent=agent)
        
        print("Starting Discord bot...")
        print("Press Ctrl+C to stop")
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def start_slack(
        self,
        token: Optional[str] = None,
        app_token: Optional[str] = None,
        agent_file: Optional[str] = None,
    ) -> None:
        """Start a Slack bot.
        
        Args:
            token: Slack bot token (or use SLACK_BOT_TOKEN env var)
            app_token: Slack app token (or use SLACK_APP_TOKEN env var)
            agent_file: Optional path to agent configuration file
        """
        token = token or os.environ.get("SLACK_BOT_TOKEN")
        app_token = app_token or os.environ.get("SLACK_APP_TOKEN")
        
        if not token:
            print("Error: Slack bot token required")
            print("Provide via --token or SLACK_BOT_TOKEN environment variable")
            return
        
        try:
            from praisonai.bots import SlackBot
        except ImportError as e:
            print(f"Error: SlackBot requires slack-bolt. {e}")
            print("Install with: pip install slack-bolt")
            return
        
        agent = self._load_agent(agent_file)
        bot = SlackBot(token=token, app_token=app_token, agent=agent)
        
        print("Starting Slack bot...")
        print("Press Ctrl+C to stop")
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def _load_agent(self, file_path: Optional[str]):
        """Load agent from configuration file."""
        if not file_path:
            from praisonaiagents import Agent
            return Agent(name="assistant", instructions="You are a helpful assistant.")
        
        if not os.path.exists(file_path):
            print(f"Warning: Agent file not found: {file_path}")
            from praisonaiagents import Agent
            return Agent(name="assistant", instructions="You are a helpful assistant.")
        
        try:
            import yaml
            with open(file_path, "r") as f:
                config = yaml.safe_load(f)
            
            from praisonaiagents import Agent
            
            if "agents" in config and config["agents"]:
                agent_config = config["agents"][0]
            else:
                agent_config = config
            
            return Agent(
                name=agent_config.get("name", "assistant"),
                instructions=agent_config.get("instructions", "You are a helpful assistant."),
                llm=agent_config.get("llm"),
            )
        except Exception as e:
            print(f"Error loading agent: {e}")
            from praisonaiagents import Agent
            return Agent(name="assistant", instructions="You are a helpful assistant.")


def handle_bot_command(args) -> None:
    """Handle bot CLI command."""
    handler = BotHandler()
    
    platform = getattr(args, "platform", None)
    
    if platform == "telegram":
        handler.start_telegram(
            token=getattr(args, "token", None),
            agent_file=getattr(args, "agent", None),
        )
    elif platform == "discord":
        handler.start_discord(
            token=getattr(args, "token", None),
            agent_file=getattr(args, "agent", None),
        )
    elif platform == "slack":
        handler.start_slack(
            token=getattr(args, "token", None),
            app_token=getattr(args, "app_token", None),
            agent_file=getattr(args, "agent", None),
        )
    else:
        print("Available platforms: telegram, discord, slack")
        print("Usage: praisonai bot <platform> [options]")


def add_bot_parser(subparsers) -> None:
    """Add bot subparser to CLI."""
    bot_parser = subparsers.add_parser(
        "bot",
        help="Start a messaging bot",
    )
    
    bot_subparsers = bot_parser.add_subparsers(
        dest="platform",
        help="Bot platform",
    )
    
    telegram_parser = bot_subparsers.add_parser(
        "telegram",
        help="Start a Telegram bot",
    )
    telegram_parser.add_argument(
        "--token",
        help="Telegram bot token (or use TELEGRAM_BOT_TOKEN env var)",
    )
    telegram_parser.add_argument(
        "--agent",
        help="Path to agent configuration file",
    )
    
    discord_parser = bot_subparsers.add_parser(
        "discord",
        help="Start a Discord bot",
    )
    discord_parser.add_argument(
        "--token",
        help="Discord bot token (or use DISCORD_BOT_TOKEN env var)",
    )
    discord_parser.add_argument(
        "--agent",
        help="Path to agent configuration file",
    )
    
    slack_parser = bot_subparsers.add_parser(
        "slack",
        help="Start a Slack bot",
    )
    slack_parser.add_argument(
        "--token",
        help="Slack bot token (or use SLACK_BOT_TOKEN env var)",
    )
    slack_parser.add_argument(
        "--app-token",
        dest="app_token",
        help="Slack app token for Socket Mode (or use SLACK_APP_TOKEN env var)",
    )
    slack_parser.add_argument(
        "--agent",
        help="Path to agent configuration file",
    )
    
    bot_parser.set_defaults(func=handle_bot_command)
