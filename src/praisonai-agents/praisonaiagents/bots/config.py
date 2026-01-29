"""
Bot Configuration for PraisonAI Agents.

Provides configuration dataclasses for bot settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BotConfig:
    """Configuration for messaging bots.
    
    Attributes:
        token: Bot authentication token
        webhook_url: URL for webhook mode (optional)
        webhook_path: Path for webhook endpoint
        polling_interval: Interval for polling mode (seconds)
        allowed_users: List of allowed user IDs (empty = all allowed)
        allowed_channels: List of allowed channel IDs (empty = all allowed)
        command_prefix: Prefix for commands (default: "/")
        mention_required: Whether bot mention is required in groups
        typing_indicator: Whether to show typing indicator
        max_message_length: Maximum message length before splitting
        retry_attempts: Number of retry attempts for failed operations
        timeout: Request timeout in seconds
        metadata: Additional platform-specific configuration
    """
    
    token: str = ""
    webhook_url: Optional[str] = None
    webhook_path: str = "/webhook"
    polling_interval: float = 1.0
    allowed_users: List[str] = field(default_factory=list)
    allowed_channels: List[str] = field(default_factory=list)
    command_prefix: str = "/"
    mention_required: bool = True
    typing_indicator: bool = True
    max_message_length: int = 4096
    retry_attempts: int = 3
    timeout: int = 30
    reply_in_thread: bool = False  # Default to inline, set True for thread replies
    thread_threshold: int = 500  # Auto-thread responses longer than this (0 = disabled)
    
    # Default tools enabled for all bots
    default_tools: List[str] = field(default_factory=lambda: ["execute_command", "search_web"])
    
    # Auto-approve tool calls (useful for trusted environments)
    auto_approve_tools: bool = False  # If True, skip confirmation for tool execution
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "token": "***" if self.token else None,
            "webhook_url": self.webhook_url,
            "webhook_path": self.webhook_path,
            "polling_interval": self.polling_interval,
            "allowed_users": self.allowed_users,
            "allowed_channels": self.allowed_channels,
            "command_prefix": self.command_prefix,
            "mention_required": self.mention_required,
            "typing_indicator": self.typing_indicator,
            "max_message_length": self.max_message_length,
            "retry_attempts": self.retry_attempts,
            "timeout": self.timeout,
            "reply_in_thread": self.reply_in_thread,
            "thread_threshold": self.thread_threshold,
            "default_tools": self.default_tools,
            "auto_approve_tools": self.auto_approve_tools,
            "metadata": self.metadata,
        }
    
    @property
    def is_webhook_mode(self) -> bool:
        """Whether bot is configured for webhook mode."""
        return bool(self.webhook_url)
    
    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to interact with the bot."""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users
    
    def is_channel_allowed(self, channel_id: str) -> bool:
        """Check if a channel is allowed for bot interaction."""
        if not self.allowed_channels:
            return True
        return channel_id in self.allowed_channels
