"""
Pydantic-based config schema validation for bot.yaml / gateway.yaml.

Provides clear, human-friendly error messages when configuration is invalid.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentConfigSchema(BaseModel):
    """Schema for agent configuration in bot.yaml."""
    name: str = "assistant"
    instructions: str = ""
    model: str = "gpt-4o-mini"
    memory: bool = False
    tools: List[str] = Field(default_factory=list)


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


class SessionConfigSchema(BaseModel):
    """Schema for session configuration."""
    max_history: int = 100
    reset: Optional[SessionResetConfigSchema] = None


class StreamingConfigSchema(BaseModel):
    """Schema for streaming reply configuration."""
    mode: str = "off"  # off | draft | progress
    min_interval: float = 1.5  # Minimum seconds between edits
    min_delta: int = 120  # Minimum character delta before edit
    placeholder_text: str = "🤔 Thinking..."
    progress_prefix: str = "🤔 "
    
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


class ChannelConfigSchema(BaseModel):
    """Schema for a single channel configuration."""
    platform: Optional[str] = None
    token: str = ""
    mode: str = "poll"  # poll | ws | webhook | hybrid
    group_policy: str = "respond_all"  # respond_all, mention_only, command_only
    allowlist: List[str] = Field(default_factory=list)
    blocklist: List[str] = Field(default_factory=list)
    allowed_users: Optional[str] = None
    admin_users: Optional[str] = None  # Comma-separated list of admin user IDs
    user_allowed_commands: Optional[str] = None  # Comma-separated list of allowed commands
    routes: Dict[str, str] = Field(default_factory=dict)
    webhook_url: Optional[str] = None
    webhook_port: int = 8080
    streaming: Optional[StreamingConfigSchema] = None
    home_channel: Optional[str] = None  # Default channel for this platform
    aliases: Dict[str, str] = Field(default_factory=dict)  # Friendly name -> channel_id mapping
    outbound_resilience: Optional[OutboundResilienceSchema] = None
    session: Optional[SessionConfigSchema] = None
    max_history: Optional[int] = None  # Backward compatibility
    
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


class BotYamlSchema(BaseModel):
    """Full schema for bot.yaml configuration."""
    agent: Optional[AgentConfigSchema] = None
    channels: Dict[str, ChannelConfigSchema] = Field(default_factory=dict)
    routing: Optional[RoutingConfigSchema] = None
    daemon: Optional[DaemonConfigSchema] = None
    
    @model_validator(mode="after")
    def validate_channels_exist(self):
        """Ensure at least one channel is configured."""
        if not self.channels:
            raise ValueError(
                "No channels configured. Add at least one channel "
                "(telegram, discord, slack, whatsapp) to your bot.yaml"
            )
        # Channel keys may be platform names (telegram) or custom ids (telegram_cfo)
        # when ``platform`` is set on the channel block (gateway / multi-bot YAML).
        valid_platforms = {"telegram", "discord", "slack", "whatsapp", "email", "agentmail"}
        for name, channel in self.channels.items():
            platform = (channel.platform or name).lower()
            if platform not in valid_platforms:
                raise ValueError(
                    f"Unknown channel '{name}' (platform '{platform}'). "
                    f"Supported platforms: {', '.join(sorted(valid_platforms))}"
                )
        return self


def validate_bot_config(raw: Dict[str, Any]) -> BotYamlSchema:
    """Validate a raw YAML dict against the bot config schema.
    
    Args:
        raw: Parsed YAML dictionary
        
    Returns:
        Validated BotYamlSchema
        
    Raises:
        ValueError: With human-friendly error messages
    """
    try:
        return BotYamlSchema(**raw)
    except Exception as e:
        # Re-raise with user-friendly message
        msg = str(e)
        # Strip pydantic internals for cleaner output
        if "validation error" in msg.lower():
            lines = msg.split("\n")
            clean_lines = [line for line in lines if line.strip() and not line.strip().startswith("For further")]
            msg = "\n".join(clean_lines)
        raise ValueError(f"Invalid bot.yaml configuration:\n{msg}") from None


def load_and_validate_bot_yaml(path: str) -> BotYamlSchema:
    """Load and validate a bot.yaml file.
    
    Args:
        path: Path to the YAML file
        
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
    
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    
    return validate_bot_config(raw)
