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
    from .linear import LinearBot
    from .email import EmailBot
    from .agentmail import AgentMailBot
    from .bot import Bot
    from .botos import BotOS
    from ._session import BotSessionManager
    from ._identity import StoreBackedIdentityResolver
    from ._dlq import InboundDLQ, DLQEntry
    from ._dead_targets import DeadTargetRegistry, DeadTarget
    from ._ingress import InboundJournal, JournalEntry
    from ._slack_approval import SlackApproval
    from ._telegram_approval import TelegramApproval
    from ._discord_approval import DiscordApproval
    from ._webhook_approval import WebhookApproval
    from ._http_approval import HTTPApproval
    from ._streaming import StreamingConfig, StreamingMode, DraftStreamer
    from ._outbox import OutboundQueue, OutboundEntry
    from ._approval_store import ApprovalStore
    from ._delivery import DurableDelivery, deliver_with_retry
    from ._durable_adapter import DurableAdapterMixin
    from ._outbound_resilience import OutboundResilienceMixin
    from ._outbound_messenger import BotOutboundMessenger
    from ._correlation import (
        correlation_id_from,
        current_correlation_id,
        new_correlation_id,
        use_correlation_id,
    )
    from ._metrics import GatewayMetrics

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
    if name == "LinearBot":
        from .linear import LinearBot
        return LinearBot
    if name == "EmailBot":
        from .email import EmailBot
        return EmailBot
    if name == "AgentMailBot":
        from .agentmail import AgentMailBot
        return AgentMailBot
    if name == "Bot":
        from .bot import Bot
        return Bot
    if name == "BotOS":
        from .botos import BotOS
        return BotOS
    if name == "SlackApproval":
        from ._slack_approval import SlackApproval
        return SlackApproval
    if name == "TelegramApproval":
        from ._telegram_approval import TelegramApproval
        return TelegramApproval
    if name == "DiscordApproval":
        from ._discord_approval import DiscordApproval
        return DiscordApproval
    if name == "WebhookApproval":
        from ._webhook_approval import WebhookApproval
        return WebhookApproval
    if name == "HTTPApproval":
        from ._http_approval import HTTPApproval
        return HTTPApproval
    # W1 — cross-platform mirror + identity
    if name == "mirror_to_session":
        from ._mirror import mirror_to_session
        return mirror_to_session
    if name == "BotSessionManager":
        from ._session import BotSessionManager
        return BotSessionManager
    if name == "StoreBackedIdentityResolver":
        from ._identity import StoreBackedIdentityResolver
        return StoreBackedIdentityResolver
    # N4 — inbound dead-letter queue
    if name == "InboundDLQ":
        from ._dlq import InboundDLQ
        return InboundDLQ
    if name == "DLQEntry":
        from ._dlq import DLQEntry
        return DLQEntry
    # Self-healing dead-target registry (issue #2486)
    if name == "DeadTargetRegistry":
        from ._dead_targets import DeadTargetRegistry
        return DeadTargetRegistry
    if name == "DeadTarget":
        from ._dead_targets import DeadTarget
        return DeadTarget
    # Inbound message journal for durable processing
    if name == "InboundJournal":
        from ._ingress import InboundJournal
        return InboundJournal
    if name == "JournalEntry":
        from ._ingress import JournalEntry
        return JournalEntry
    # Streaming components
    if name == "StreamingConfig":
        from ._streaming import StreamingConfig
        return StreamingConfig
    if name == "StreamingMode":
        from ._streaming import StreamingMode
        return StreamingMode
    if name == "DraftStreamer":
        from ._streaming import DraftStreamer
        return DraftStreamer
    # Outbound delivery components
    if name == "OutboundQueue":
        from ._outbox import OutboundQueue
        return OutboundQueue
    if name == "OutboundEntry":
        from ._outbox import OutboundEntry
        return OutboundEntry
    if name == "ApprovalStore":
        from ._approval_store import ApprovalStore
        return ApprovalStore
    if name == "DurableDelivery":
        from ._delivery import DurableDelivery
        return DurableDelivery
    if name == "deliver_with_retry":
        from ._delivery import deliver_with_retry
        return deliver_with_retry
    if name == "deliver_chunked":
        from ._delivery import deliver_chunked
        return deliver_chunked
    if name == "DurableAdapterMixin":
        from ._durable_adapter import DurableAdapterMixin
        return DurableAdapterMixin
    if name == "OutboundResilienceMixin":
        from ._outbound_resilience import OutboundResilienceMixin
        return OutboundResilienceMixin
    if name == "BotOutboundMessenger":
        from ._outbound_messenger import BotOutboundMessenger
        return BotOutboundMessenger
    # End-to-end correlation IDs (inbound -> run -> outbound)
    if name == "correlation_id_from":
        from ._correlation import correlation_id_from
        return correlation_id_from
    if name == "current_correlation_id":
        from ._correlation import current_correlation_id
        return current_correlation_id
    if name == "new_correlation_id":
        from ._correlation import new_correlation_id
        return new_correlation_id
    if name == "use_correlation_id":
        from ._correlation import use_correlation_id
        return use_correlation_id
    # Gateway message-flow metrics
    if name == "GatewayMetrics":
        from ._metrics import GatewayMetrics
        return GatewayMetrics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "TelegramBot", "DiscordBot", "SlackBot", "WhatsAppBot", "LinearBot", "EmailBot", "AgentMailBot",
    "Bot", "BotOS",
    "BotSessionManager",
    "StoreBackedIdentityResolver",
    "InboundDLQ", "DLQEntry",
    "DeadTargetRegistry", "DeadTarget",
    "InboundJournal", "JournalEntry",
    "OutboundQueue", "OutboundEntry",
    "ApprovalStore",
    "DurableDelivery", "deliver_with_retry", "deliver_chunked",
    "DurableAdapterMixin",
    "OutboundResilienceMixin",
    "BotOutboundMessenger",
    # Correlation + metrics (gateway message-flow observability)
    "correlation_id_from", "current_correlation_id", "new_correlation_id",
    "use_correlation_id", "GatewayMetrics",
    "SlackApproval", "TelegramApproval", "DiscordApproval",
    "WebhookApproval", "HTTPApproval",
    # Streaming
    "StreamingConfig", "StreamingMode", "DraftStreamer",
    # W1
    "mirror_to_session",
]
