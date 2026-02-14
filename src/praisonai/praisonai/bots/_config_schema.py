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


class ChannelConfigSchema(BaseModel):
    """Schema for a single channel configuration."""
    token: str = ""
    group_policy: str = "respond_all"  # respond_all, mention_only, command_only
    allowlist: List[str] = Field(default_factory=list)
    blocklist: List[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    
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
        # Validate channel names
        valid_platforms = {"telegram", "discord", "slack", "whatsapp"}
        for name in self.channels:
            if name not in valid_platforms:
                raise ValueError(
                    f"Unknown channel '{name}'. Supported: {', '.join(sorted(valid_platforms))}"
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
