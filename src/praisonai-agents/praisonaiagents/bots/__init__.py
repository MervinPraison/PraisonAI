"""
Bot Protocols for PraisonAI Agents.

Provides protocols and base classes for building messaging bot implementations
(Telegram, Discord, Slack, etc.) that connect agents to messaging platforms.

This module contains only protocols and lightweight utilities.
Heavy implementations live in the praisonai wrapper package.
"""

from .protocols import (
    BotProtocol,
    BotMessageProtocol,
    BotUserProtocol,
    BotChannelProtocol,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)
from .config import BotConfig

__all__ = [
    "BotProtocol",
    "BotMessageProtocol",
    "BotUserProtocol",
    "BotChannelProtocol",
    "BotMessage",
    "BotUser",
    "BotChannel",
    "BotConfig",
    "MessageType",
]
