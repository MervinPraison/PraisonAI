"""
Bot Protocols and Configuration for PraisonAI Agents.

Defines the interfaces and configuration for messaging bot implementations.
All implementations live in the ``praisonai-bot`` package (``praisonai_bot.bots``).
Backward-compatible imports: ``from praisonai.bots import Bot`` via wrapper shims.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass
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
    WebhookVerifierProtocol,
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
    adapt_presentation,
)
from .interactive import (
    InteractiveContext,
    InteractiveRegistry,
    InteractiveHandler,
    InteractiveAuthorizer,
    encode_action,
    decode_callback,
    create_registry,
    get_registry,
    register_handler,
    unregister_handler,
    make_reply_handler,
    REPLY_NAMESPACE,
)
from .agent_reply import (
    AgentReply,
    extract_presentation,
)
from .config import BotConfig, BotOSConfig, DisplayPolicy, resolve_display_policy
from .silence import (
    SILENT_REPLY_TOKEN,
    is_intentional_silence_response,
    BotLoopPolicy,
    BotLoopGuard,
)
from .run_status import (
    RunPhase,
    RunStatusController,
    StallState,
    StallWatchdog,
)

__all__ = [
    "BotProtocol",
    "BotMessageProtocol",
    "BotUserProtocol",
    "BotChannelProtocol",
    "BotMessage",
    "BotUser",
    "BotChannel",
    "BotConfig",
    "DisplayPolicy",
    "resolve_display_policy",
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
    "adapt_presentation",
    "PlatformCapabilities",
    "WebhookVerifierProtocol",
    "InteractiveContext",
    "InteractiveRegistry",
    "InteractiveHandler",
    "InteractiveAuthorizer",
    "encode_action",
    "decode_callback",
    "create_registry",
    "get_registry",
    "register_handler",
    "unregister_handler",
    "make_reply_handler",
    "REPLY_NAMESPACE",
    "AgentReply",
    "extract_presentation",
    "SILENT_REPLY_TOKEN",
    "is_intentional_silence_response",
    "BotLoopPolicy",
    "BotLoopGuard",
    "RunPhase",
    "RunStatusController",
    "StallState",
    "StallWatchdog",
]
