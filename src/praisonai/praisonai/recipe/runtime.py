"""
Recipe Runtime Configuration Models.

Defines the runtime configuration schema for recipes, enabling:
- Background task execution
- Async job submission
- Scheduled execution (24/7 daemon)

All fields are optional and backward compatible with existing recipes.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Safe defaults for operational features
DEFAULT_TIMEOUT_SEC = 300  # 5 minutes
DEFAULT_MAX_COST_USD = 1.00  # $1.00 budget limit
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_CLEANUP_DELAY_SEC = 3600  # 1 hour


@dataclass
class BackgroundRuntimeConfig:
    """Configuration for background task execution."""
    enabled: bool = False
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    cleanup_delay_sec: int = DEFAULT_CLEANUP_DELAY_SEC
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'BackgroundRuntimeConfig':
        """Create from dictionary with defaults."""
        if not data:
            return cls()
        return cls(
            enabled=data.get('enabled', False),
            max_concurrent=data.get('max_concurrent', DEFAULT_MAX_CONCURRENT),
            cleanup_delay_sec=data.get('cleanup_delay_sec', DEFAULT_CLEANUP_DELAY_SEC),
        )


@dataclass
class JobRuntimeConfig:
    """Configuration for async job execution."""
    enabled: bool = False
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    webhook_url: Optional[str] = None  # Supports ${ENV_VAR} interpolation
    idempotency_scope: str = "none"  # none|session|global
    events: List[str] = field(default_factory=lambda: ["completed", "failed"])
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'JobRuntimeConfig':
        """Create from dictionary with defaults."""
        if not data:
            return cls()
        return cls(
            enabled=data.get('enabled', False),
            timeout_sec=data.get('timeout_sec', DEFAULT_TIMEOUT_SEC),
            webhook_url=data.get('webhook_url'),
            idempotency_scope=data.get('idempotency_scope', 'none'),
            events=data.get('events', ['completed', 'failed']),
        )


@dataclass
class ScheduleRuntimeConfig:
    """Configuration for scheduled execution."""
    enabled: bool = False
    interval: str = "hourly"  # hourly|daily|*/30m|seconds|cron-like
    max_retries: int = DEFAULT_MAX_RETRIES
    run_immediately: bool = False
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ScheduleRuntimeConfig':
        """Create from dictionary with defaults."""
        if not data:
            return cls()
        return cls(
            enabled=data.get('enabled', False),
            interval=data.get('interval', 'hourly'),
            max_retries=data.get('max_retries', DEFAULT_MAX_RETRIES),
            run_immediately=data.get('run_immediately', False),
            timeout_sec=data.get('timeout_sec', DEFAULT_TIMEOUT_SEC),
            max_cost_usd=data.get('max_cost_usd', DEFAULT_MAX_COST_USD),
        )


@dataclass
class RuntimeConfig:
    """
    Complete runtime configuration for a recipe.
    
    Parsed from the optional `runtime` block in TEMPLATE.yaml:
    
    ```yaml
    runtime:
      background:
        enabled: false
        max_concurrent: 5
        cleanup_delay_sec: 3600
      job:
        enabled: false
        timeout_sec: 3600
        webhook_url: "${WEBHOOK_URL}"
        idempotency_scope: "session"
        events: ["completed", "failed"]
      schedule:
        enabled: false
        interval: "hourly"
        max_retries: 3
        run_immediately: true
        timeout_sec: 300
        max_cost_usd: 1.00
    ```
    """
    background: BackgroundRuntimeConfig = field(default_factory=BackgroundRuntimeConfig)
    job: JobRuntimeConfig = field(default_factory=JobRuntimeConfig)
    schedule: ScheduleRuntimeConfig = field(default_factory=ScheduleRuntimeConfig)
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'RuntimeConfig':
        """Create from dictionary with defaults."""
        if not data:
            return cls()
        return cls(
            background=BackgroundRuntimeConfig.from_dict(data.get('background')),
            job=JobRuntimeConfig.from_dict(data.get('job')),
            schedule=ScheduleRuntimeConfig.from_dict(data.get('schedule')),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'background': {
                'enabled': self.background.enabled,
                'max_concurrent': self.background.max_concurrent,
                'cleanup_delay_sec': self.background.cleanup_delay_sec,
            },
            'job': {
                'enabled': self.job.enabled,
                'timeout_sec': self.job.timeout_sec,
                'webhook_url': self.job.webhook_url,
                'idempotency_scope': self.job.idempotency_scope,
                'events': self.job.events,
            },
            'schedule': {
                'enabled': self.schedule.enabled,
                'interval': self.schedule.interval,
                'max_retries': self.schedule.max_retries,
                'run_immediately': self.schedule.run_immediately,
                'timeout_sec': self.schedule.timeout_sec,
                'max_cost_usd': self.schedule.max_cost_usd,
            },
        }


def expand_env_vars(value: Any) -> Any:
    """
    Safely expand environment variables in a value.
    
    Only supports ${VAR} syntax for safety (no eval, no shell expansion).
    
    Args:
        value: Value to expand (string, dict, or list)
        
    Returns:
        Value with environment variables expanded
    """
    if isinstance(value, str):
        # Match ${VAR} pattern only
        pattern = r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'
        
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))  # Keep original if not found
        
        return re.sub(pattern, replace_env, value)
    
    elif isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    
    return value


def parse_runtime_config(
    raw_runtime: Optional[Dict[str, Any]],
    expand_env: bool = True
) -> RuntimeConfig:
    """
    Parse runtime configuration from raw YAML data.
    
    Args:
        raw_runtime: Raw runtime dict from TEMPLATE.yaml
        expand_env: Whether to expand environment variables
        
    Returns:
        Parsed RuntimeConfig with defaults applied
    """
    if not raw_runtime:
        return RuntimeConfig()
    
    # Expand environment variables if requested
    if expand_env:
        raw_runtime = expand_env_vars(raw_runtime)
    
    return RuntimeConfig.from_dict(raw_runtime)
