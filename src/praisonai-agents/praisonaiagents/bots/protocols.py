"""
Bot Protocols for PraisonAI Agents.

Defines the interfaces for messaging bot implementations.
These protocols enable agents to communicate through messaging platforms
like Telegram, Discord, Slack, etc.

All implementations should live in the praisonai wrapper package.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    TypedDict,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from ..agent import Agent


class ChannelCapabilities(TypedDict, total=False):
    """Declares what features a bot channel supports.
    
    This allows shared engines to adapt behavior based on platform capabilities,
    enabling graceful degradation when features aren't available.
    
    Attributes:
        live_edit: Whether the channel supports editing messages in place
        reactions: Whether the channel supports adding reactions to messages
        typing: Whether the channel supports typing indicators
        text_limit: Maximum message length (0 = unlimited)
        edit_rate_limit: Minimum seconds between edits (for throttling)
        reaction_rate_limit: Minimum seconds between reactions
    """
    live_edit: bool
    reactions: bool
    typing: bool
    text_limit: int
    edit_rate_limit: float
    reaction_rate_limit: float


class RunStatus(Enum):
    """Run status states for progress feedback.
    
    Used by status engines to show agent execution state through
    reactions or status lines.
    """
    QUEUED = "queued"
    THINKING = "thinking"
    TOOL = "tool"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class PlatformCapabilities:
    """Platform-specific capabilities descriptor for bot adapters.
    
    Declares what a messaging platform can do, enabling the shared delivery
    machinery to apply features like streaming, rate limiting, and chunking
    uniformly across all platforms.
    
    Attributes:
        max_message_length: Maximum message length in the platform's unit
        length_unit: Unit for message length ("codepoints" or "utf16")
        supports_edit: Whether the platform supports in-place message edits (for streaming)
        supports_typing: Whether the platform supports typing indicators
        markdown_dialect: Markdown flavor the platform uses (e.g., "markdown", "telegram_markdown_v2")
        needs_rate_limit: Whether the platform needs rate limiting
        edit_interval_ms: Minimum milliseconds between message edits (for streaming)
        max_files_per_message: Maximum number of file attachments per message
        max_file_size_mb: Maximum file size in megabytes
        supported_file_types: List of supported file extensions/mime types
        accepts_webhooks: Whether the platform delivers inbound messages via webhook
        verifies_webhook_signature: Whether the adapter verifies inbound webhook
            authenticity. Adapters that accept webhooks MUST set this True and
            expose a ``webhook_verifier`` so central ingress can enforce it
            fail-closed.
        reconciles_unknown_send: Whether the adapter can confirm whether a prior
            send attempt actually landed (e.g. via a provider message-status
            lookup keyed on the idempotency key). When True the durable outbox
            reconciles an in-flight (``sending``) entry on restart before
            re-dispatch, upgrading delivery from at-least-once to
            effectively-once. When False, delivery remains at-least-once and a
            crash mid-send may re-send the message.
        supports_idempotency_token: Whether the transport accepts a
            provider-level idempotency token so the platform itself
            de-duplicates a retried send. This is an informational capability
            descriptor only; the durable outbox does not forward a token on
            resend, so adapters relying on provider-side dedupe should also set
            ``reconciles_unknown_send`` to get effectively-once delivery.
    """
    
    max_message_length: int = 4096
    length_unit: str = "codepoints"  # "codepoints" or "utf16"
    supports_edit: bool = False
    supports_typing: bool = True
    markdown_dialect: str = "markdown"
    needs_rate_limit: bool = True
    edit_interval_ms: int = 1000  # Minimum ms between edits
    max_files_per_message: int = 1
    max_file_size_mb: int = 10
    supported_file_types: List[str] = field(default_factory=lambda: ["*"])
    accepts_webhooks: bool = False
    verifies_webhook_signature: bool = False
    reconciles_unknown_send: bool = False
    supports_idempotency_token: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_message_length": self.max_message_length,
            "length_unit": self.length_unit,
            "supports_edit": self.supports_edit,
            "supports_typing": self.supports_typing,
            "markdown_dialect": self.markdown_dialect,
            "needs_rate_limit": self.needs_rate_limit,
            "edit_interval_ms": self.edit_interval_ms,
            "max_files_per_message": self.max_files_per_message,
            "max_file_size_mb": self.max_file_size_mb,
            "supported_file_types": self.supported_file_types,
            "accepts_webhooks": self.accepts_webhooks,
            "verifies_webhook_signature": self.verifies_webhook_signature,
            "reconciles_unknown_send": self.reconciles_unknown_send,
            "supports_idempotency_token": self.supports_idempotency_token,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformCapabilities":
        """Create from dictionary."""
        return cls(
            max_message_length=data.get("max_message_length", 4096),
            length_unit=data.get("length_unit", "codepoints"),
            supports_edit=data.get("supports_edit", False),
            supports_typing=data.get("supports_typing", True),
            markdown_dialect=data.get("markdown_dialect", "markdown"),
            needs_rate_limit=data.get("needs_rate_limit", True),
            edit_interval_ms=data.get("edit_interval_ms", 1000),
            max_files_per_message=data.get("max_files_per_message", 1),
            max_file_size_mb=data.get("max_file_size_mb", 10),
            supported_file_types=data.get("supported_file_types", ["*"]),
            accepts_webhooks=data.get("accepts_webhooks", False),
            verifies_webhook_signature=data.get("verifies_webhook_signature", False),
            reconciles_unknown_send=data.get("reconciles_unknown_send", False),
            supports_idempotency_token=data.get("supports_idempotency_token", False),
        )


@runtime_checkable
class WebhookVerifierProtocol(Protocol):
    """Protocol for verifying inbound webhook authenticity.

    Internet-facing bot adapters (Slack, WhatsApp, Linear, AgentMail, …)
    receive webhooks that must be authenticated before they become an agent
    run. This protocol declares the contract so the wrapper ingress can
    enforce verification centrally and fail-closed: an adapter that declares
    ``PlatformCapabilities.accepts_webhooks`` must expose a verifier and that
    verifier must pass before dispatch.

    Implementations live in the ``praisonai`` wrapper package and typically
    wrap an HMAC comparison over the raw request body.

    Example:
        class SlackVerifier:
            def verify(self, *, headers, raw_body):
                ...
    """

    def verify(self, *, headers: Mapping[str, str], raw_body: bytes) -> bool:
        """Return True if the inbound webhook is authentic.

        Args:
            headers: Inbound request headers (case-insensitive mapping).
            raw_body: The exact raw request body bytes (pre-parse).

        Returns:
            True if the signature/secret verifies, False otherwise.
        """
        ...


class MessageType(str, Enum):
    """Types of bot messages."""
    
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    LOCATION = "location"
    STICKER = "sticker"
    COMMAND = "command"
    CALLBACK = "callback"
    REACTION = "reaction"
    REPLY = "reply"
    EDIT = "edit"
    DELETE = "delete"


@dataclass
class BotUser:
    """Represents a user in a messaging platform.
    
    Attributes:
        user_id: Platform-specific user identifier
        username: User's username (if available)
        display_name: User's display name
        is_bot: Whether this user is a bot
        metadata: Additional platform-specific metadata
    """
    
    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    is_bot: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "is_bot": self.is_bot,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotUser":
        """Create from dictionary."""
        return cls(
            user_id=data.get("user_id", "unknown"),
            username=data.get("username"),
            display_name=data.get("display_name"),
            is_bot=data.get("is_bot", False),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BotChannel:
    """Represents a channel/chat in a messaging platform.
    
    Attributes:
        channel_id: Platform-specific channel identifier
        name: Channel name (if available)
        channel_type: Type of channel (dm, group, channel, thread)
        metadata: Additional platform-specific metadata
    """
    
    channel_id: str
    name: Optional[str] = None
    channel_type: str = "dm"  # dm, group, channel, thread
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "channel_type": self.channel_type,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotChannel":
        """Create from dictionary."""
        return cls(
            channel_id=data.get("channel_id", "unknown"),
            name=data.get("name"),
            channel_type=data.get("channel_type", "dm"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BotMessage:
    """Represents a message in a messaging platform.
    
    Attributes:
        message_id: Platform-specific message identifier
        content: Message content (text or structured data)
        message_type: Type of message
        sender: User who sent the message
        channel: Channel where the message was sent
        timestamp: Message timestamp
        reply_to: ID of message being replied to
        thread_id: Thread identifier (for threaded conversations)
        attachments: List of attachment URLs or data
        metadata: Additional platform-specific metadata
    """
    
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: Union[str, Dict[str, Any]] = ""
    message_type: MessageType = MessageType.TEXT
    sender: Optional[BotUser] = None
    channel: Optional[BotChannel] = None
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "message_type": self.message_type.value if isinstance(self.message_type, MessageType) else self.message_type,
            "sender": self.sender.to_dict() if self.sender else None,
            "channel": self.channel.to_dict() if self.channel else None,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
            "thread_id": self.thread_id,
            "attachments": self.attachments,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotMessage":
        """Create from dictionary."""
        msg_type = data.get("message_type", "text")
        try:
            msg_type = MessageType(msg_type)
        except ValueError:
            msg_type = MessageType.TEXT
        
        sender_data = data.get("sender")
        channel_data = data.get("channel")
        
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            content=data.get("content", ""),
            message_type=msg_type,
            sender=BotUser.from_dict(sender_data) if sender_data else None,
            channel=BotChannel.from_dict(channel_data) if channel_data else None,
            timestamp=data.get("timestamp", time.time()),
            reply_to=data.get("reply_to"),
            thread_id=data.get("thread_id"),
            attachments=data.get("attachments", []),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def text(self) -> str:
        """Get message text content."""
        if isinstance(self.content, str):
            return self.content
        return self.content.get("text", "")
    
    @property
    def is_command(self) -> bool:
        """Check if message is a command."""
        return self.message_type == MessageType.COMMAND or (
            isinstance(self.content, str) and self.content.startswith("/")
        )
    
    @property
    def command(self) -> Optional[str]:
        """Extract command name if this is a command message."""
        if not self.is_command:
            return None
        text = self.text
        if text.startswith("/"):
            return text.split()[0][1:]  # Remove "/" and get first word
        return None
    
    @property
    def command_args(self) -> List[str]:
        """Extract command arguments if this is a command message."""
        if not self.is_command:
            return []
        text = self.text
        parts = text.split()
        return parts[1:] if len(parts) > 1 else []


@runtime_checkable
class BotMessageProtocol(Protocol):
    """Protocol for bot message handling."""
    
    @property
    def message_id(self) -> str:
        """Unique message identifier."""
        ...
    
    @property
    def content(self) -> Union[str, Dict[str, Any]]:
        """Message content."""
        ...
    
    @property
    def sender(self) -> Optional[BotUser]:
        """Message sender."""
        ...
    
    @property
    def channel(self) -> Optional[BotChannel]:
        """Message channel."""
        ...


@runtime_checkable
class BotUserProtocol(Protocol):
    """Protocol for bot user representation."""
    
    @property
    def user_id(self) -> str:
        """Unique user identifier."""
        ...
    
    @property
    def username(self) -> Optional[str]:
        """User's username."""
        ...
    
    @property
    def is_bot(self) -> bool:
        """Whether this user is a bot."""
        ...


@runtime_checkable
class BotChannelProtocol(Protocol):
    """Protocol for bot channel representation."""
    
    @property
    def channel_id(self) -> str:
        """Unique channel identifier."""
        ...
    
    @property
    def channel_type(self) -> str:
        """Type of channel (dm, group, channel, thread)."""
        ...


@dataclass
class ProbeResult:
    """Result of a channel connectivity probe.
    
    Attributes:
        ok: Whether the probe succeeded
        platform: Platform name
        elapsed_ms: Time taken in milliseconds
        bot_username: Bot's username (if available)
        error: Error message (if probe failed)
        details: Additional platform-specific details
    """
    
    ok: bool
    platform: str = ""
    elapsed_ms: float = 0.0
    bot_username: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ok": self.ok,
            "platform": self.platform,
            "elapsed_ms": self.elapsed_ms,
            "bot_username": self.bot_username,
            "error": self.error,
            "details": self.details,
        }


class HealthReason(Enum):
    """Reasons for channel health status."""
    HEALTHY = "healthy"
    NOT_RUNNING = "not-running"
    DISCONNECTED = "disconnected"
    STALE_SOCKET = "stale-socket"
    STUCK = "stuck"
    BUSY = "busy"
    STARTUP_GRACE = "startup-grace"
    ERROR = "error"
    
    @property
    def is_recoverable(self) -> bool:
        """Whether this reason indicates a recoverable state."""
        return self in {
            HealthReason.DISCONNECTED,
            HealthReason.STALE_SOCKET,
            HealthReason.STUCK,
            HealthReason.ERROR,
        }


def evaluate_channel_health(
    health: HealthResult,
    startup_grace_seconds: float = 60.0,
    stale_after_seconds: float = 120.0,
    current_time: Optional[float] = None,
) -> HealthReason:
    """Evaluate channel health and return a reason.
    
    Pure function that evaluates a HealthResult and determines
    the health reason based on various criteria.
    
    Args:
        health: The health result to evaluate
        startup_grace_seconds: Grace period for startup
        stale_after_seconds: Time after which no activity is considered stale
        current_time: Current timestamp (for testing)
        
    Returns:
        HealthReason indicating the channel's health status
    """
    if current_time is None:
        current_time = time.time()
    
    # Not running
    if not health.is_running:
        return HealthReason.NOT_RUNNING
    
    # Startup grace period
    if health.uptime_seconds is not None and health.uptime_seconds < startup_grace_seconds:
        return HealthReason.STARTUP_GRACE
    
    # Check for errors
    if health.error:
        return HealthReason.ERROR
    
    # Check probe result
    if health.probe and not health.probe.ok:
        return HealthReason.DISCONNECTED
    
    # Check for stale socket (no transport activity)
    if health.last_activity is not None:
        time_since_activity = current_time - health.last_activity
        if time_since_activity > stale_after_seconds:
            return HealthReason.STALE_SOCKET
    
    # Overall health status
    if not health.ok:
        return HealthReason.ERROR
    
    return HealthReason.HEALTHY


@dataclass
class HealthResult:
    """Detailed health status of a bot.
    
    Attributes:
        ok: Overall health status
        platform: Platform name
        is_running: Whether the bot is actively running
        uptime_seconds: Seconds since bot started (None if not running)
        probe: Latest probe result (None if not probed)
        sessions: Number of active sessions
        error: Error message (if unhealthy)
        details: Additional platform-specific health details
        reason: Health status reason (optional)
        last_activity: Last transport activity timestamp (optional)
    """
    
    ok: bool
    platform: str = ""
    is_running: bool = False
    uptime_seconds: Optional[float] = None
    probe: Optional[ProbeResult] = None
    sessions: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[HealthReason] = None
    last_activity: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ok": self.ok,
            "platform": self.platform,
            "is_running": self.is_running,
            "uptime_seconds": self.uptime_seconds,
            "probe": self.probe.to_dict() if self.probe else None,
            "sessions": self.sessions,
            "error": self.error,
            "details": self.details,
            "reason": self.reason.value if self.reason else None,
            "last_activity": self.last_activity,
        }


@runtime_checkable
class BotProtocol(Protocol):
    """Protocol for messaging bot implementations.
    
    Bots connect agents to messaging platforms, handling:
    - Message receiving and sending
    - Command handling
    - Webhook/polling management
    - User and channel management
    
    Example usage (implementation in praisonai wrapper):
        from praisonai.bots import TelegramBot
        
        bot = TelegramBot(token="...", agent=my_agent)
        await bot.start()
    """
    
    @property
    def is_running(self) -> bool:
        """Whether the bot is currently running."""
        ...
    
    @property
    def platform(self) -> str:
        """Platform name (telegram, discord, slack, etc.)."""
        ...
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        """The bot's user information."""
        ...
    
    @property
    def capabilities(self) -> ChannelCapabilities:
        """Channel capabilities for feature discovery.
        
        Returns capabilities that shared engines use to adapt behavior.
        Channels that don't support a feature should return False for it.
        """
        ...
    
    @property
    def platform_capabilities(self) -> PlatformCapabilities:
        """Platform capabilities descriptor.
        
        Returns the platform's capabilities for use by shared delivery code.
        Adapters should override this to declare their specific capabilities.
        """
        ...
    
    # Lifecycle methods
    async def start(self) -> None:
        """Start the bot (begin receiving messages)."""
        ...
    
    async def stop(self) -> None:
        """Stop the bot."""
        ...
    
    # Agent management
    def set_agent(self, agent: "Agent") -> None:
        """Set the agent that handles messages.
        
        Args:
            agent: The agent to handle incoming messages
        """
        ...
    
    def get_agent(self) -> Optional["Agent"]:
        """Get the current agent."""
        ...
    
    # Message handling
    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> BotMessage:
        """Send a message to a channel.
        
        Args:
            channel_id: Target channel ID
            content: Message content
            reply_to: Optional message ID to reply to
            thread_id: Optional thread ID for threaded replies
            
        Returns:
            The sent message
        """
        ...
    
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: Union[str, Dict[str, Any]],
    ) -> BotMessage:
        """Edit an existing message.
        
        Args:
            channel_id: Channel containing the message
            message_id: ID of message to edit
            content: New message content
            
        Returns:
            The edited message
        """
        ...
    
    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> bool:
        """Delete a message.
        
        Args:
            channel_id: Channel containing the message
            message_id: ID of message to delete
            
        Returns:
            True if deleted successfully
        """
        ...
    
    # Event handlers
    def on_message(self, handler: Callable[[BotMessage], Any]) -> Callable:
        """Register a message handler.
        
        Args:
            handler: Function to call when a message is received
            
        Returns:
            The handler function (for decorator use)
        """
        ...
    
    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler.
        
        Args:
            command: Command name (without /)
            
        Example:
            @bot.on_command("help")
            async def handle_help(message: BotMessage):
                await bot.send_message(message.channel.channel_id, "Help text...")
        """
        ...
    
    # Typing indicator
    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator to a channel.
        
        Args:
            channel_id: Target channel ID
        """
        ...
    
    # Reactions
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction emoji to a message.
        
        Args:
            channel_id: Channel containing the message
            message_id: Message to react to
            emoji: Emoji to add (Unicode or custom emoji ID)
            
        Returns:
            True if reaction was added successfully
        """
        ...
    
    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Remove a reaction emoji from a message.
        
        Args:
            channel_id: Channel containing the message
            message_id: Message to remove reaction from
            emoji: Emoji to remove
            
        Returns:
            True if reaction was removed successfully
        """
        ...
    
    # User/channel info
    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user information.
        
        Args:
            user_id: User ID to look up
            
        Returns:
            User information or None if not found
        """
        ...
    
    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel information.
        
        Args:
            channel_id: Channel ID to look up
            
        Returns:
            Channel information or None if not found
        """
        ...
    
    # Health & diagnostics
    async def probe(self) -> ProbeResult:
        """Test channel connectivity without starting the bot.
        
        Verifies the bot token is valid and the platform API is reachable.
        
        Returns:
            ProbeResult with connectivity status and bot info.
        """
        ...
    
    async def health(self) -> HealthResult:
        """Get detailed health status of the running bot.
        
        Returns:
            HealthResult with running state, uptime, probe, and session count.
        """
        ...


@dataclass
class ChatCommandInfo:
    """Metadata for a registered chat command.
    
    Attributes:
        name: Command name (without /)
        description: Human-readable description
        usage: Usage example (e.g., "/status")
        hidden: Whether to hide from /help listing
    """
    
    name: str
    description: str = ""
    usage: Optional[str] = None
    hidden: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "usage": self.usage,
            "hidden": self.hidden,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatCommandInfo":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            usage=data.get("usage"),
            hidden=data.get("hidden", False),
        )


@runtime_checkable
class ChatCommandProtocol(Protocol):
    """Protocol for bots that support standardized chat commands.
    
    Extends BotProtocol with chat command registration and listing.
    Implementations should track registered commands and expose them
    for /help listings and command dispatching.
    """
    
    def register_command(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: Optional[str] = None,
    ) -> None:
        """Register a chat command handler.
        
        Args:
            name: Command name (without /)
            handler: Async callable to handle the command
            description: Human-readable description
            usage: Usage example string
        """
        ...
    
    def list_commands(self) -> List[ChatCommandInfo]:
        """List all registered chat commands.
        
        Returns:
            List of ChatCommandInfo for all registered commands
        """
        ...


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SupportsPresentation — interactive UI presentation protocol
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@runtime_checkable
class SupportsPresentation(Protocol):
    """Protocol for channel adapters that support presentations.
    
    Channel adapters implement this protocol to render
    portable presentations as native widgets.
    """
    
    @property
    def presentation_limits(self) -> "PresentationLimits":
        """Get channel-specific presentation limits."""
        ...
    
    async def render_presentation(
        self,
        target: str,
        presentation: "MessagePresentation",
    ) -> Optional[str]:
        """Render a presentation to a target (chat/channel).
        
        Args:
            target: Target identifier (chat_id, channel_id, etc.)
            presentation: The presentation to render
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        ...
    
    def truncate_presentation(
        self,
        presentation: "MessagePresentation",
    ) -> "MessagePresentation":
        """Truncate a presentation to fit channel limits.
        
        Args:
            presentation: The presentation to truncate
            
        Returns:
            Truncated presentation that fits channel limits
        """
        ...


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EmailProtocol — email-specific bot capabilities
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class EmailInbox:
    """Information about an email inbox.
    
    Attributes:
        id: Unique inbox identifier
        email_address: The inbox's email address
        domain: Domain of the inbox
        created_at: When the inbox was created (ISO format)
    """
    
    id: str
    email_address: str
    domain: str = ""
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "email_address": self.email_address,
            "domain": self.domain,
            "created_at": self.created_at,
        }


@runtime_checkable
class EmailProtocol(Protocol):
    """Protocol for email bots with inbox lifecycle management.
    
    Extends BotProtocol with email-specific capabilities like
    programmatic inbox creation, listing, and deletion.
    
    This protocol is optional — only AgentMail-style bots that
    support API-based inbox management need to implement it.
    Traditional IMAP/SMTP bots (EmailBot) do not implement this.
    
    Example:
        # Check if a bot supports inbox management
        if isinstance(bot, EmailProtocol):
            inbox = await bot.create_inbox(domain="mycompany.com")
            print(f"Created: {inbox['email_address']}")
    """
    
    @property
    def email_address(self) -> Optional[str]:
        """The bot's current email address."""
        ...
    
    async def create_inbox(
        self,
        domain: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new email inbox programmatically.
        
        Args:
            domain: Optional custom domain for the inbox
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dict with at least 'id' and 'email_address' keys
        """
        ...
    
    async def list_inboxes(self) -> List[Dict[str, Any]]:
        """List all inboxes accessible to this bot.
        
        Returns:
            List of inbox dicts with 'id' and 'email_address' keys
        """
        ...
    
    async def delete_inbox(self, inbox_id: str) -> bool:
        """Delete an inbox.
        
        Args:
            inbox_id: ID of the inbox to delete
            
        Returns:
            True if deleted successfully
        """
        ...


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BotOS Protocol — multi-platform bot orchestration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@runtime_checkable
class BotOSProtocol(Protocol):
    """Protocol for BotOS — multi-platform bot orchestrator.

    BotOS manages multiple Bot instances across different messaging
    platforms (Telegram, Discord, Slack, WhatsApp, etc.) with a single
    unified lifecycle.

    Hierarchy::

        BotOS  (multi-platform orchestrator)
        └── Bot  (single platform)
            └── Agent / AgentTeam / AgentFlow  (AI brain)

    Implementations live in the ``praisonai`` wrapper package.
    """

    @property
    def is_running(self) -> bool:
        """Whether the orchestrator is currently running."""
        ...

    async def start(self) -> None:
        """Start all registered bots concurrently."""
        ...

    async def stop(self) -> None:
        """Gracefully stop all running bots."""
        ...

    def add_bot(self, bot: Any) -> None:
        """Register a Bot instance for orchestration.

        Args:
            bot: A Bot instance (satisfies BotProtocol).
        """
        ...

    def list_bots(self) -> List[str]:
        """List platform names of all registered bots.

        Returns:
            List of platform name strings.
        """
        ...

    def remove_bot(self, platform: str) -> bool:
        """Remove a registered bot by platform name.

        Args:
            platform: Platform identifier to remove.

        Returns:
            True if removed, False if not found.
        """
        ...

    def get_bot(self, platform: str) -> Optional[Any]:
        """Get a registered bot by platform name.

        Args:
            platform: Platform identifier (e.g. "telegram").

        Returns:
            The Bot instance, or None if not found.
        """
        ...
