"""
Bot implementations for PraisonAI.

Provides messaging bot runtimes for Telegram, Discord, Slack, and WhatsApp,
plus the user-friendly Bot and BotOS orchestrator classes.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram import TelegramBot
    from .discord import DiscordBot
    from .slack import SlackBot
    from .whatsapp import WhatsAppBot
    from .bot import Bot
    from .botos import BotOS

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
    if name == "WhatsAppBot":
        from .whatsapp import WhatsAppBot
        return WhatsAppBot
    if name == "Bot":
        from .bot import Bot
        return Bot
    if name == "BotOS":
        from .botos import BotOS
        return BotOS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "TelegramBot", "DiscordBot", "SlackBot", "WhatsAppBot",
    "Bot", "BotOS",
]
