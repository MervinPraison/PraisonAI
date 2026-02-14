"""
Bot Protocols and Configuration for PraisonAI Agents.

Defines the interfaces and configuration for messaging bot implementations.
All implementations live in the praisonai wrapper package.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import (
        BotOSProtocol,  # noqa: F401
        BotProtocol,
        BotMessageProtocol,
        BotUserProtocol,
        BotChannelProtocol,
        BotMessage,
        BotUser,
        BotChannel,
        MessageType,
        ChatCommandInfo,
        ChatCommandProtocol,
        ProbeResult,
        HealthResult,
    )
from .protocols import (
    BotProtocol,
    BotMessageProtocol,
    BotUserProtocol,
    BotChannelProtocol,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
    ChatCommandInfo,
    ChatCommandProtocol,
    BotOSProtocol,
    ProbeResult,
    HealthResult,
)
from .config import BotConfig, BotOSConfig

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
    "ChatCommandInfo",
    "ChatCommandProtocol",
    "BotOSProtocol",
    "BotOSConfig",
    "ProbeResult",
    "HealthResult",
]
