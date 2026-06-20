"""
Bot Protocols and Configuration for PraisonAI Agents.

Defines the interfaces and configuration for messaging bot implementations.
All implementations live in the praisonai wrapper package.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import BotOSProtocol  # noqa: F401
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
    EmailProtocol,
    EmailInbox,
    SupportsPresentation,
    PlatformCapabilities,
)
from .presentation import (
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    SelectOption,
    PresentationLimits,
    ActionType,
    ButtonStyle,
    BlockType,
)
from .interactive import (
    InteractiveContext,
    InteractiveRegistry,
    InteractiveHandler,
    encode_action,
    decode_callback,
    create_registry,
    get_registry,
    register_handler,
    unregister_handler,
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
    "EmailProtocol",
    "EmailInbox",
    "MessagePresentation",
    "PresentationBlock",
    "PresentationButton",
    "PresentationAction",
    "SelectOption",
    "PresentationLimits",
    "SupportsPresentation",
    "ActionType",
    "ButtonStyle",
    "BlockType",
    "PlatformCapabilities",
    "InteractiveContext",
    "InteractiveRegistry",
    "InteractiveHandler",
    "encode_action",
    "decode_callback",
    "create_registry",
    "get_registry",
    "register_handler",
    "unregister_handler",
]
