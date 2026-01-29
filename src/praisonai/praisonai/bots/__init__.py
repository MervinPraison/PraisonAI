"""
Bot implementations for PraisonAI.

Provides messaging bot runtimes for Telegram, Discord, and Slack.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram import TelegramBot
    from .discord import DiscordBot
    from .slack import SlackBot

def __getattr__(name: str):
    """Lazy loading of bot components."""
    if name == "TelegramBot":
        from .telegram import TelegramBot
        return TelegramBot
    if name == "DiscordBot":
        from .discord import DiscordBot
        return DiscordBot
    if name == "SlackBot":
        from .slack import SlackBot
        return SlackBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["TelegramBot", "DiscordBot", "SlackBot"]
