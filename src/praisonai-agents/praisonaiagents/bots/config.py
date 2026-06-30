"""
Bot Configuration for PraisonAI Agents.

Provides configuration dataclasses for bot settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .pairing_types import UnknownUserPolicy


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
        # Clarify tool (new from main)
        "clarify",
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
    
    # In-flight run control settings for mid-run message handling
    # busy_mode: Policy for handling messages during active runs
    #   - "queue": Queue message for next turn (default)
    #   - "interrupt": Cancel current run and start new one  
    #   - "steer": Inject message into current run via steering
    busy_mode: str = "queue"
    
    # Template for busy acknowledgment messages (use {action} placeholder)
    busy_ack: str = "⏳ {action} — will be considered next"
    
    # Workspace settings for file operation containment and security
    workspace_dir: Optional[str] = None  # default: ~/.praisonai/workspaces/<scope>/<session_key>
    workspace_access: str = "rw"  # "rw" (read-write) | "ro" (read-only) | "none" (copy-on-write sandbox)
    workspace_scope: str = "session"  # "shared" | "session" | "user" | "agent"
    
    # Unknown user policy: "deny" (default), "pair", or "allow"
    unknown_user_policy: UnknownUserPolicy = "deny"
    
    # Owner user ID for pairing approvals (platform-specific format)
    owner_user_id: Optional[str] = None
    
    # Progressive streaming for channel bots (default: False)
    streaming: bool = False
    
    # Edit interval for streaming responses in milliseconds (default: 700ms)
    stream_edit_interval_ms: int = 700
    
    # Intentional silence support
    allow_silence: bool = False
    silence_token: Optional[str] = None

    def __post_init__(self) -> None:
        if self.unknown_user_policy not in {"deny", "pair", "allow"}:
            raise ValueError(
                f"unknown_user_policy must be one of: deny, pair, allow. Got: {self.unknown_user_policy}"
            )
    
    
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
            "busy_mode": self.busy_mode,
            "busy_ack": self.busy_ack,
            "workspace_dir": self.workspace_dir,
            "workspace_access": self.workspace_access,
            "workspace_scope": self.workspace_scope,
            "unknown_user_policy": self.unknown_user_policy,
            "owner_user_id": "***" if self.owner_user_id else None,
            "streaming": self.streaming,
            "stream_edit_interval_ms": self.stream_edit_interval_ms,
            "allow_silence": self.allow_silence,
            "silence_token": self.silence_token,
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


# ---------------------------------------------------------------------------
# Display / verbosity policy
# ---------------------------------------------------------------------------

# Allowed values for each DisplayPolicy field.
_DISPLAY_STREAMING = {"off", "draft", "progress"}
_DISPLAY_TOOL_PROGRESS = {"off", "inline"}
_DISPLAY_FOOTER = {"off", "compact"}

# Platform → tier mapping. Tiers describe the rendering surface so sensible
# defaults can be applied without per-platform configuration.
#   edit   — edit-capable personal chats (stream live, hide tool spam)
#   work   — workspace chats (post discrete progress steps)
#   noedit — no-edit chats (single final message)
#   batch  — batch-only channels (one final message, no interim)
_PLATFORM_TIERS: Dict[str, str] = {
    "telegram": "edit",
    "discord": "edit",
    "whatsapp": "noedit",
    "slack": "work",
    "teams": "work",
    "mattermost": "work",
    "email": "batch",
    "sms": "batch",
}


@dataclass
class DisplayPolicy:
    """Per-platform display / verbosity policy.

    Describes the operator's *policy* for how output should be presented on a
    channel (as opposed to ``PlatformCapabilities`` which describes what a
    platform *can* render).

    Attributes:
        streaming: Reply streaming mode.
            ``"off"`` (single final message) | ``"draft"`` (edit in place) |
            ``"progress"`` (compact status then final).
        tool_progress: Whether tool execution progress is surfaced.
            ``"off"`` (hidden) | ``"inline"`` (inline progress bubbles).
        interim_assistant_messages: Show partial assistant messages, or only
            the final reply.
        footer: Runtime footer / status-line appended to replies.
            ``"off"`` | ``"compact"`` (e.g. ``model · ctx% · cwd``).
    """

    streaming: str = "off"
    tool_progress: str = "off"
    interim_assistant_messages: bool = False
    footer: str = "off"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "streaming": self.streaming,
            "tool_progress": self.tool_progress,
            "interim_assistant_messages": self.interim_assistant_messages,
            "footer": self.footer,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisplayPolicy":
        """Create a policy from a (partial) dict, ignoring unknown keys."""
        base = cls()
        return cls(
            streaming=_coerce_choice(
                data.get("streaming", base.streaming), _DISPLAY_STREAMING, base.streaming
            ),
            tool_progress=_coerce_choice(
                data.get("tool_progress", base.tool_progress),
                _DISPLAY_TOOL_PROGRESS,
                base.tool_progress,
            ),
            interim_assistant_messages=bool(
                data.get("interim_assistant_messages", base.interim_assistant_messages)
            ),
            footer=_coerce_choice(
                data.get("footer", base.footer), _DISPLAY_FOOTER, base.footer
            ),
        )


# Built-in per-tier defaults. Most operators configure nothing and still get
# correct UX on every channel.
_TIER_DEFAULTS: Dict[str, DisplayPolicy] = {
    # edit-capable personal chats: stream live, hide tool spam, no footer
    "edit": DisplayPolicy(streaming="draft", tool_progress="off", footer="off"),
    # workspace chats: post discrete progress steps
    "work": DisplayPolicy(streaming="off", tool_progress="inline", footer="off"),
    # no-edit chats: single final message
    "noedit": DisplayPolicy(streaming="off", tool_progress="off", footer="off"),
    # batch-only channels: one final message, no interim
    "batch": DisplayPolicy(
        streaming="off",
        tool_progress="off",
        interim_assistant_messages=False,
        footer="off",
    ),
}


def _coerce_choice(value: Any, allowed: set, default: str) -> str:
    """Return ``value`` if it is an allowed choice, else ``default``."""
    if isinstance(value, str) and value in allowed:
        return value
    return default


def resolve_display_policy(platform: str, config: Optional[Dict[str, Any]]) -> DisplayPolicy:
    """Resolve the effective :class:`DisplayPolicy` for a platform.

    Precedence (highest first):
        1. explicit ``display.platforms.<platform>.<setting>``
        2. ``display.<setting>`` global default
        3. platform-tier default (edit / work / noedit / batch)
        4. built-in :class:`DisplayPolicy` default

    Args:
        platform: Platform name, e.g. ``"telegram"``.
        config: A ``display`` config dict (the value of the ``display:`` block),
            or a full config dict containing a ``display`` key. ``None`` is
            treated as empty.

    Returns:
        The resolved :class:`DisplayPolicy`.
    """
    display = _extract_display(config)

    # Layer 4: built-in default.
    policy = DisplayPolicy()

    # Layer 3: platform-tier default.
    tier = _PLATFORM_TIERS.get((platform or "").lower())
    if tier and tier in _TIER_DEFAULTS:
        policy = _merge_policy(policy, _TIER_DEFAULTS[tier].to_dict())

    # Layer 2: global default (display.<setting>).
    global_overrides = {
        k: v for k, v in display.items() if k != "platforms"
    }
    policy = _merge_policy(policy, global_overrides)

    # Layer 1: explicit platform override.
    platforms = display.get("platforms") or {}
    if isinstance(platforms, dict):
        platform_overrides = platforms.get(platform) or platforms.get(
            (platform or "").lower()
        )
        if isinstance(platform_overrides, dict):
            policy = _merge_policy(policy, platform_overrides)

    return policy


def _extract_display(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the ``display`` mapping from ``config``.

    Accepts either the ``display`` block directly or a full config dict
    containing a ``display`` key.
    """
    if not isinstance(config, dict):
        return {}
    if "display" in config and isinstance(config.get("display"), dict):
        return config["display"]
    return config


def _merge_policy(policy: DisplayPolicy, overrides: Dict[str, Any]) -> DisplayPolicy:
    """Return a new policy with valid ``overrides`` applied over ``policy``."""
    if not isinstance(overrides, dict):
        return policy
    data = policy.to_dict()
    for key in data:
        if key in overrides:
            data[key] = overrides[key]
    return DisplayPolicy.from_dict(data)


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
