"""
Pydantic-based config schema validation for bot.yaml / gateway.yaml.

Provides clear, human-friendly error messages when configuration is invalid.
This is the canonical configuration schema for all bot/gateway configurations.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class AgentConfigSchema(BaseModel):
    """Schema for agent configuration in bot.yaml."""
    name: str = "assistant"
    instructions: str = ""
    model: Optional[str] = "gpt-4o-mini"
    llm: Optional[str] = None  # Alias for model
    memory: bool = False
    tools: List[str] = Field(default_factory=list)
    knowledge: Union[bool, List[str]] = False
    web_search: bool = False
    web_search_provider: str = "duckduckgo"
    auto_approve: bool = False
    
    @model_validator(mode="after")
    def handle_model_aliases(self):
        """Handle model/llm aliases."""
        # Use llm if provided and model wasn't explicitly set
        if self.llm and "model" not in self.model_fields_set:
            self.model = self.llm
        return self


class SessionResetConfigSchema(BaseModel):
    """Schema for session reset policy configuration."""
    mode: str = "none"  # none | idle | daily | both
    idle_minutes: int = 60  # Reset after N minutes of inactivity
    at_hour: Optional[int] = None  # Daily reset hour (0-23)
    
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"none", "idle", "daily", "both"}
        if v not in allowed:
            raise ValueError(
                f"Invalid reset mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("idle_minutes")
    @classmethod
    def validate_idle_minutes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("idle_minutes must be at least 1")
        return v
    
    @field_validator("at_hour")
    @classmethod
    def validate_at_hour(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("at_hour must be between 0 and 23")
        return v
    
    @model_validator(mode="after")
    def validate_config_consistency(self):
        """Ensure at_hour is set when mode requires it."""
        if self.mode in ("daily", "both") and self.at_hour is None:
            raise ValueError(f"at_hour is required when mode is '{self.mode}'")
        return self


class SessionCompactionConfigSchema(BaseModel):
    """Schema for session history compaction configuration.

    When enabled, older turns in a long-lived bot/gateway session are
    summarised (rather than hard-truncated) once the history exceeds the
    configured budget, so context survives across weeks-long conversations
    and restarts. Disabled by default to preserve legacy behaviour.
    """
    enabled: bool = False
    strategy: str = "summarize"  # truncate | sliding | summarize | smart | prune | llm_summarize
    max_messages: int = 100  # Approx. compaction threshold (converted to a token budget; max_history remains a hard cap)
    max_tokens: Optional[int] = None  # Optional token-based budget (overrides messages)
    keep_recent: int = 10  # Number of most-recent messages kept verbatim

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"truncate", "sliding", "summarize", "smart", "prune", "llm_summarize"}
        if v not in allowed:
            raise ValueError(
                f"Invalid compaction strategy '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("max_messages")
    @classmethod
    def validate_max_messages(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_messages must be at least 1")
        return v

    @field_validator("keep_recent")
    @classmethod
    def validate_keep_recent(cls, v: int) -> int:
        if v < 0:
            raise ValueError("keep_recent must be non-negative")
        return v


class SessionConfigSchema(BaseModel):
    """Schema for session configuration."""
    max_history: int = 100
    reset: Optional[SessionResetConfigSchema] = None
    compaction: Optional[SessionCompactionConfigSchema] = None
    # Group/channel session scope (Issue #2376). ``per_user`` (default) keeps
    # today's per-sender isolation; ``per_chat`` routes group/channel messages
    # to a single shared session so the agent follows one multi-party thread.
    session_scope: str = "per_user"
    # Sender-attribution template applied to each turn in per_chat scope.
    # Supports ``{sender}`` and ``{time}`` placeholders.
    attribution: str = "[{sender}] "

    @field_validator("session_scope")
    @classmethod
    def validate_session_scope(cls, v: str) -> str:
        allowed = {"per_user", "per_chat"}
        if v not in allowed:
            raise ValueError(
                f"Invalid session_scope '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class StreamingConfigSchema(BaseModel):
    """Schema for streaming reply configuration."""
    mode: str = "off"  # off | draft | progress
    min_interval: float = 1.5  # Minimum seconds between edits
    min_delta: int = 120  # Minimum character delta before edit
    placeholder_text: str = "🤔 Thinking..."
    progress_prefix: str = "🤔 "
    # Progress rendering style: "line" (single overwritten tool line) or
    # "feed" (bounded multi-line rolling status feed). Applies to progress mode.
    progress_style: str = "line"
    progress_max_lines: int = 8  # Max trailing lines shown in feed style
    progress_max_line_chars: int = 120  # Per-line char cap in feed style
    # Flood-control / resilience for progressive edits
    disable_progressive_edits_after: int = 3  # Consecutive edit failures before giving up
    flood_backoff_factor: float = 2.0  # Multiply interval on each flood/429
    max_interval: float = 30.0  # Cap for the adaptively-widened interval
    strip_reasoning_tags: bool = True  # Strip <think>/<reasoning> from output
    
    @field_validator("mode")
    @classmethod
    def validate_streaming_mode(cls, v: str) -> str:
        allowed = {"off", "draft", "progress"}
        if v not in allowed:
            raise ValueError(
                f"Invalid streaming mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("min_interval")
    @classmethod
    def validate_min_interval(cls, v: float) -> float:
        if v < 0.1:
            raise ValueError("min_interval must be at least 0.1 seconds")
        return v
    
    @field_validator("min_delta")
    @classmethod
    def validate_min_delta(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_delta must be at least 1 character")
        return v

    @field_validator("progress_style")
    @classmethod
    def validate_progress_style(cls, v: str) -> str:
        allowed = {"line", "feed"}
        if v not in allowed:
            raise ValueError(
                f"Invalid progress_style '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class OutboundResilienceSchema(BaseModel):
    """Schema for outbound message retry configuration."""
    enabled: bool = True
    initial_ms: float = 1000.0  # Initial retry delay in ms
    max_ms: float = 10000.0  # Maximum retry delay in ms
    factor: float = 1.5  # Exponential backoff factor
    max_attempts: int = 3  # Maximum retry attempts
    jitter: float = 0.25  # Random jitter fraction
    dlq_path: Optional[str] = None  # Path to outbound DLQ database
    
    @field_validator("initial_ms")
    @classmethod
    def validate_initial_ms(cls, v: float) -> float:
        if v < 100:
            raise ValueError("initial_ms must be at least 100ms")
        return v
    
    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        return v


class DeliveryConfigSchema(BaseModel):
    """Schema for durable inbound/outbound delivery configuration.

    Durability is **on by default** for long-running gateway/bot runs: a
    deduplicating inbound journal and an inbound dead-letter queue are wired
    against a single canonical per-agent SQLite store so a crash mid-turn or a
    platform webhook redelivery never silently loses or double-processes a
    message. Advanced operators can override the store location or disable
    durability entirely.
    """
    durable: bool = True  # default on for gateway/bot runs
    store: Optional[str] = None  # optional canonical SQLite store override


class ChannelConfigSchema(BaseModel):
    """Schema for a single channel configuration."""
    platform: Optional[str] = None
    token: str = ""
    app_token: Optional[str] = None  # For Slack Socket Mode
    mode: str = "poll"  # poll | ws | webhook | hybrid
    group_policy: str = "mention_only"  # Default to secure: respond_all, mention_only, command_only
    allow_silence: bool = False  # Allow agent to return NO_REPLY to stay silent
    silence_token: Optional[str] = None  # Custom silence token (defaults to NO_REPLY)
    allowlist: List[str] = Field(default_factory=list)
    blocklist: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)  # Changed to List for consistency
    admin_users: Optional[str] = None  # Comma-separated list of admin user IDs
    user_allowed_commands: Optional[str] = None  # Comma-separated list of allowed commands
    routes: Dict[str, str] = Field(default_factory=dict)  # Context -> agent_id mapping
    routing: Optional[Dict[str, str]] = None  # Alias for routes
    bindings: List[Dict[str, Any]] = Field(default_factory=list)  # Priority-ordered route bindings (Issue #2225)
    webhook_url: Optional[str] = None
    webhook_port: int = 8080
    streaming: Optional[StreamingConfigSchema] = None
    home_channel: Optional[str] = None  # Default channel for this platform
    aliases: Dict[str, str] = Field(default_factory=dict)  # Friendly name -> channel_id mapping
    outbound_resilience: Optional[OutboundResilienceSchema] = None
    delivery: Optional[DeliveryConfigSchema] = None  # Durable inbound/outbound delivery
    session: Optional[SessionConfigSchema] = None
    max_history: Optional[int] = None  # Backward compatibility
    # Inbound media (Issue #2350): when a user sends a photo/document/video,
    # adapters download and validate it (SSRF-safe, magic-byte checked) and
    # forward the cached path to the agent's vision capability. Set to 0 to
    # disable inbound media handling.
    max_inbound_media_bytes: int = Field(default=20 * 1024 * 1024, ge=0)
    
    # Platform-specific fields
    phone_number_id: Optional[str] = None  # WhatsApp
    verify_token: Optional[str] = None  # WhatsApp
    whatsapp_mode: Optional[str] = None  # WhatsApp-specific mode: "cloud" or "web"
    creds_dir: Optional[str] = None  # WhatsApp web mode credentials directory
    email_address: Optional[str] = None  # Email
    imap_server: Optional[str] = None  # Email  
    smtp_server: Optional[str] = None  # Email
    inbox_id: Optional[str] = None  # AgentMail
    domain: Optional[str] = None  # AgentMail
    
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"poll", "ws", "webhook", "hybrid"}
        if v not in allowed:
            raise ValueError(
                f"Invalid mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("token")
    @classmethod
    def resolve_env_var(cls, v: str) -> str:
        """Resolve ${ENV_VAR} references in token."""
        if v.startswith("${") and v.endswith("}"):
            env_key = v[2:-1]
            resolved = os.environ.get(env_key, "")
            if not resolved:
                raise ValueError(
                    f"Environment variable '{env_key}' not set. "
                    f"Set it with: export {env_key}=your_token"
                )
            return resolved
        return v
    
    @field_validator("group_policy")
    @classmethod
    def validate_group_policy(cls, v: str) -> str:
        allowed = {"respond_all", "mention_only", "command_only"}
        if v not in allowed:
            raise ValueError(
                f"Invalid group_policy '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @model_validator(mode="after")
    def validate_security(self):
        """Validate security settings and warn about unsafe configurations."""
        # Merge routing and routes
        if self.routing and not self.routes:
            self.routes = self.routing
            
        # Warn about empty allowed_users (open to everyone)
        if not self.allowed_users and not self.allowlist and not self.blocklist:
            logger.warning(
                "Channel has no user restrictions (allowed_users/allowlist/blocklist). "
                "Bot will respond to EVERYONE. Consider adding allowed_users for security."
            )
            
        # Warn about respond_all in production
        if self.group_policy == "respond_all":
            logger.warning(
                "Channel uses 'respond_all' group_policy. "
                "Consider 'mention_only' for better security."
            )
        return self


class RoutingConfigSchema(BaseModel):
    """Schema for agent routing configuration."""
    default: str = "assistant"
    rules: Dict[str, str] = Field(default_factory=dict)


class DaemonConfigSchema(BaseModel):
    """Schema for daemon/service configuration."""
    enabled: bool = False
    restart: str = "always"  # always, on_failure, never
    
    @field_validator("restart")
    @classmethod
    def validate_restart(cls, v: str) -> str:
        allowed = {"always", "on_failure", "never"}
        if v not in allowed:
            raise ValueError(f"Invalid restart policy '{v}'. Must be one of: {', '.join(sorted(allowed))}")
        return v


class GatewayConfigSchema(BaseModel):
    """Unified schema for gateway.yaml/bot.yaml configuration.
    
    This is the canonical schema that supports all configuration patterns:
    - Single-bot bot.yaml (platform + token + agent)
    - Gateway gateway.yaml (agents dict + channels dict with routing)
    - BotOS config (agent + platforms dict)
    """
    # Top-level fields for single-bot compatibility
    platform: Optional[str] = None
    token: Optional[str] = None
    
    # Agent configuration (single or multiple)
    agent: Optional[AgentConfigSchema] = None
    agents: Optional[Dict[str, AgentConfigSchema]] = None
    
    # Channel configuration
    channels: Dict[str, ChannelConfigSchema] = Field(default_factory=dict)
    
    # Platform dict for BotOS compatibility
    platforms: Optional[Dict[str, Dict[str, Any]]] = None
    
    # Routing and daemon config
    routing: Optional[RoutingConfigSchema] = None
    daemon: Optional[DaemonConfigSchema] = None

    # Gateway server settings (host/port, drain_timeout, admission control,
    # etc.) and inbound trigger hooks. These are read by
    # ``gateway/server.py::load_gateway_config`` / ``_apply_hooks_from_config``
    # rather than modelled field-by-field here; kept permissive so a real
    # ``gateway.yaml`` with a top-level ``gateway:``/``hooks:`` block validates
    # through this single schema instead of being rejected. See issue #2585.
    gateway: Optional[Dict[str, Any]] = None
    hooks: Optional[List[Dict[str, Any]]] = None
    
    @model_validator(mode="after")
    def normalize_and_validate(self):
        """Normalize different config formats to canonical form and validate."""
        # Migrate single-bot format (platform + token at top level)
        if self.platform and self.token and not self.channels:
            self.channels = {
                self.platform: ChannelConfigSchema(
                    platform=self.platform,
                    token=self.token
                )
            }
            
        # Migrate BotOS platforms format to channels
        if self.platforms and not self.channels:
            for platform_name, platform_config in self.platforms.items():
                self.channels[platform_name] = ChannelConfigSchema(
                    platform=platform_name,
                    **platform_config
                )
                
        # Ensure at least one channel is configured
        if not self.channels:
            raise ValueError(
                "No channels configured. Add at least one channel "
                "(telegram, discord, slack, whatsapp) to your config"
            )
            
        # Validate platform names against the platform registry (single source
        # of truth). This includes built-in platforms, entry-point discovered
        # channels (``praisonai.channels`` / ``praisonai.bots``), and any
        # channel registered at runtime via ``register_platform()``.
        try:
            from ._registry import list_platforms
            valid_platforms = set(list_platforms())
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Platform registry unavailable; falling back to built-in "
                "platform list.", exc_info=True
            )
            # Fall back to the built-in set (single source of truth) if the
            # registry is unavailable.
            try:
                from ._registry import _BUILTIN_PLATFORMS
                valid_platforms = set(_BUILTIN_PLATFORMS)
            except Exception:
                valid_platforms = {
                    "telegram", "discord", "slack", "whatsapp",
                    "email", "agentmail", "linear",
                }
        for name, channel in self.channels.items():
            platform = (channel.platform or name).lower()
            if platform not in valid_platforms:
                raise ValueError(
                    f"Unknown channel '{name}' (platform '{platform}'). "
                    f"Supported platforms: {', '.join(sorted(valid_platforms))}"
                )
                
        # Set platform if not explicitly set
        for name, channel in self.channels.items():
            if not channel.platform:
                channel.platform = name
                
        return self


# Legacy alias for backward compatibility
BotYamlSchema = GatewayConfigSchema


def validate_gateway_config(raw: Dict[str, Any], apply_env_substitution: bool = True) -> GatewayConfigSchema:
    """Validate a raw YAML dict against the unified gateway config schema.
    
    Args:
        raw: Parsed YAML dictionary
        apply_env_substitution: Whether to apply ${VAR} substitution
        
    Returns:
        Validated GatewayConfigSchema
        
    Raises:
        ValueError: With human-friendly error messages
    """
    # Apply environment variable substitution if requested
    if apply_env_substitution:
        from praisonai_bot._code_bridge import import_code_module

        substitute_env_vars = import_code_module("praisonai_code.cli.utils.env_utils").substitute_env_vars
        raw = substitute_env_vars(raw)
        
    try:
        return GatewayConfigSchema(**raw)
    except Exception as e:
        # Re-raise with user-friendly message
        msg = str(e)
        # Strip pydantic internals for cleaner output
        if "validation error" in msg.lower():
            lines = msg.split("\n")
            clean_lines = [line for line in lines if line.strip() and not line.strip().startswith("For further")]
            msg = "\n".join(clean_lines)
        raise ValueError(f"Invalid gateway/bot configuration:\n{msg}") from None


def validate_bot_config(raw: Dict[str, Any]) -> GatewayConfigSchema:
    """Validate a raw YAML dict against the bot config schema.
    
    Legacy function for backward compatibility.
    
    Args:
        raw: Parsed YAML dictionary
        
    Returns:
        Validated GatewayConfigSchema
        
    Raises:
        ValueError: With human-friendly error messages
    """
    return validate_gateway_config(raw)


def load_and_validate_gateway_yaml(path: str, apply_env_substitution: bool = True) -> GatewayConfigSchema:
    """Load and validate a gateway.yaml or bot.yaml file.
    
    This is the canonical loader for all bot/gateway configurations.
    
    Args:
        path: Path to the YAML file
        apply_env_substitution: Whether to apply ${VAR} substitution
        
    Returns:
        Validated config schema
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If config is invalid
    """
    import yaml
    
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Run 'praisonai onboard' to create one, or create it manually."
        )
    
    # Load env file if not already loaded
    from praisonai_bot._code_bridge import import_code_module

    load_env_file = import_code_module("praisonai_code.cli.utils.env_utils").load_env_file
    load_env_file()
    
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    
    return validate_gateway_config(raw, apply_env_substitution)


def load_and_validate_bot_yaml(path: str) -> GatewayConfigSchema:
    """Load and validate a bot.yaml file.
    
    Legacy function for backward compatibility.
    
    Args:
        path: Path to the YAML file
        
    Returns:
        Validated config schema
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If config is invalid
    """
    return load_and_validate_gateway_yaml(path)


def migrate_legacy_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy configuration formats to the canonical schema.
    
    Handles migration from:
    - Old single-bot format (top-level platform/token)
    - Old BotOS format (platforms dict)
    - Old gateway format (missing security defaults)
    
    Args:
        raw: Raw configuration dictionary
        
    Returns:
        Migrated configuration dictionary
    """
    migrated = dict(raw)
    
    # Log migrations for transparency
    migrations = []
    
    # Migrate old allowed_users string to list
    if "channels" in migrated:
        for channel_name, channel in migrated["channels"].items():
            if isinstance(channel.get("allowed_users"), str):
                old_value = channel["allowed_users"]
                if old_value:
                    channel["allowed_users"] = [u.strip() for u in old_value.split(",") if u.strip()]
                else:
                    channel["allowed_users"] = []
                migrations.append(f"Migrated {channel_name}.allowed_users from string to list")
                
            # Set secure defaults if not specified
            if "group_policy" not in channel:
                channel["group_policy"] = "mention_only"
                migrations.append(f"Set {channel_name}.group_policy to secure default 'mention_only'")
                
    # Log any migrations performed
    if migrations:
        logger.info(f"Config migrations applied: {'; '.join(migrations)}")
        
    return migrated
