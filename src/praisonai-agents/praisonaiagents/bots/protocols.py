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
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from ..agent import Agent


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
    """
    
    ok: bool
    platform: str = ""
    is_running: bool = False
    uptime_seconds: Optional[float] = None
    probe: Optional[ProbeResult] = None
    sessions: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
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
