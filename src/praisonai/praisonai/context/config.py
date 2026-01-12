"""
Configuration for Dynamic Context Discovery.

Provides a unified configuration class for all dynamic context features.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from praisonaiagents.context.artifacts import QueueConfig


@dataclass
class DynamicContextConfig:
    """
    Configuration for Dynamic Context Discovery features.
    
    Controls:
    - Artifact storage location
    - Tool output queuing thresholds
    - History persistence
    - Terminal logging
    - Secret redaction
    
    Example:
        config = DynamicContextConfig(
            base_dir="~/.praison/runs",
            inline_max_kb=32,
            redact_secrets=True,
            terminal_logging=True,
        )
    """
    # Storage
    base_dir: str = "~/.praison/runs"
    
    # Tool output queuing
    queuing_enabled: bool = True
    inline_max_kb: int = 32
    
    # History
    history_enabled: bool = True
    
    # Terminal logging
    terminal_logging: bool = False  # Off by default for privacy
    
    # Security
    redact_secrets: bool = True
    secret_patterns: List[str] = field(default_factory=list)
    
    # Run identification
    run_id: Optional[str] = None
    
    def __post_init__(self):
        """Apply environment variable overrides."""
        self.base_dir = os.getenv(
            "PRAISONAI_ARTIFACT_DIR",
            self.base_dir
        )
        self.inline_max_kb = int(os.getenv(
            "PRAISONAI_ARTIFACT_INLINE_MAX_KB",
            str(self.inline_max_kb)
        ))
        self.redact_secrets = os.getenv(
            "PRAISONAI_ARTIFACT_REDACT",
            str(self.redact_secrets)
        ).lower() in ("true", "1", "yes")
        self.terminal_logging = os.getenv(
            "PRAISONAI_TERMINAL_LOGGING",
            str(self.terminal_logging)
        ).lower() in ("true", "1", "yes")
    
    def to_queue_config(self) -> QueueConfig:
        """Convert to QueueConfig for artifact store."""
        return QueueConfig(
            enabled=self.queuing_enabled,
            inline_max_bytes=self.inline_max_kb * 1024,
            redact_secrets=self.redact_secrets,
            secret_patterns=self.secret_patterns if self.secret_patterns else QueueConfig().secret_patterns,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "base_dir": self.base_dir,
            "queuing_enabled": self.queuing_enabled,
            "inline_max_kb": self.inline_max_kb,
            "history_enabled": self.history_enabled,
            "terminal_logging": self.terminal_logging,
            "redact_secrets": self.redact_secrets,
            "run_id": self.run_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DynamicContextConfig":
        """Create from dictionary."""
        return cls(
            base_dir=data.get("base_dir", "~/.praison/runs"),
            queuing_enabled=data.get("queuing_enabled", True),
            inline_max_kb=data.get("inline_max_kb", 32),
            history_enabled=data.get("history_enabled", True),
            terminal_logging=data.get("terminal_logging", False),
            redact_secrets=data.get("redact_secrets", True),
            secret_patterns=data.get("secret_patterns", []),
            run_id=data.get("run_id"),
        )
    
    @classmethod
    def from_env(cls) -> "DynamicContextConfig":
        """Create configuration from environment variables."""
        return cls()  # __post_init__ handles env vars
