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
    mode: str = "poll"  # poll | ws | webhook | hybrid
    webhook_url: Optional[str] = None
    webhook_path: str = "/webhook"
    webhook_port: int = 8080
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
    
    # Group message policy
    group_policy: str = "mention_only"  # respond_all, mention_only, command_only
    
    # Default safe tools (auto-injected for bots with no tools configured)
    # With workspace scoping, file operations are now safe by construction
    default_tools: List[str] = field(default_factory=lambda: [
        # Web (existing)
        "search_web", "web_crawl",
        # Memory / learning (existing)
        "store_memory", "search_memory",
        "store_learning", "search_learning",
        # Scheduling (existing)
        "schedule_add", "schedule_list", "schedule_remove",
        # Files — NEW (workspace-scoped, safe by construction)
        "read_file", "write_file", "edit_file", "list_files", "search_files",
        # Planning — NEW
        "todo_add", "todo_list", "todo_update",
        # Skills (self-improving) — NEW
        "skills_list", "skill_view", "skill_manage",
        # Delegation & session tools are intentionally NOT auto-injected yet;
        # their reference implementations are placeholders. Users can opt in
        # via BotConfig(default_tools=[..., "delegate_task", "session_search"]).
    ])
    
    # Auto-approve tool calls (useful for trusted environments)
    # Default to True for chat bots - they can't show CLI approval prompts
    auto_approve_tools: bool = True  # If True, skip confirmation for safe tool execution
    
    # Inbound message debounce (ms). Coalesces rapid messages from same user.
    # 0 = disabled (default). Recommended: 1000-2000 for chat bots.
    debounce_ms: int = 0
    
    # Ack emoji reaction on inbound messages. Empty string = disabled.
    # When set, bot reacts with this emoji on receive (e.g. "⏳") and
    # replaces it with done_emoji on completion (e.g. "✅").
    ack_emoji: str = ""
    done_emoji: str = "✅"
    
    # Session TTL in seconds. 0 = disabled (sessions never expire).
    # When set, stale sessions older than this are auto-reaped.
    session_ttl: int = 0
    
    # Workspace settings for file operation containment and security
    workspace_dir: Optional[str] = None  # default: ~/.praisonai/workspaces/<scope>/<session_key>
    workspace_access: str = "rw"  # "rw" (read-write) | "ro" (read-only) | "none" (copy-on-write sandbox)
    workspace_scope: str = "session"  # "shared" | "session" | "user" | "agent"
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "token": "***" if self.token else None,
            "mode": self.mode,
            "webhook_url": self.webhook_url,
            "webhook_path": self.webhook_path,
            "webhook_port": self.webhook_port,
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
            "debounce_ms": self.debounce_ms,
            "ack_emoji": self.ack_emoji,
            "done_emoji": self.done_emoji,
            "session_ttl": self.session_ttl,
            "workspace_dir": self.workspace_dir,
            "workspace_access": self.workspace_access,
            "workspace_scope": self.workspace_scope,
            "metadata": self.metadata,
        }
    
    @property
    def is_webhook_mode(self) -> bool:
        """Whether bot is configured for webhook mode."""
        return self.mode == "webhook" or bool(self.webhook_url)
    
    @property
    def is_ws_mode(self) -> bool:
        """Whether bot is configured for WebSocket mode."""
        return self.mode == "ws"
    
    @property
    def is_hybrid_mode(self) -> bool:
        """Whether bot is configured for hybrid mode (WS + slow poll)."""
        return self.mode == "hybrid"
    
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


@dataclass
class BotOSConfig:
    """Configuration for BotOS — multi-platform bot orchestrator.

    Attributes:
        name: Human-readable name for this BotOS instance.
        platforms: Per-platform config dicts keyed by platform name.
            Example: ``{"telegram": {"token": "..."}, "discord": {"token": "..."}}``
    """

    name: str = "PraisonAI BotOS"
    platforms: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (hides tokens)."""
        sanitized_platforms = {}
        for plat, cfg in self.platforms.items():
            sanitized = dict(cfg)
            if "token" in sanitized:
                sanitized["token"] = "***"
            sanitized_platforms[plat] = sanitized
        return {
            "name": self.name,
            "platforms": sanitized_platforms,
        }
