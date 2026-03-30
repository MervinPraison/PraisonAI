"""
Unified Configuration Resolver for PraisonAI.

This module provides a centralized, protocol-driven configuration system that:
- Unifies all environment variable access
- Provides caching for performance  
- Implements clear precedence rules
- Maintains backward compatibility
- Enables configuration validation and discovery

Design Philosophy (from AGENTS.md):
- Protocol-driven core: Use protocols for extension points
- No performance impact: Lazy loading, caching
- Agent-centric: All decisions prioritize agents and workflows
- Backward compatible: Existing env var access continues to work

Usage:
    from praisonaiagents.config.resolver import get_config, ConfigRegistry
    
    # Get a configuration value with fallback
    api_key = get_config("OPENAI_API_KEY", default=None)
    
    # Register a new configuration
    ConfigRegistry.register("MY_CONFIG", default="default_value", doc="My config setting")
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Protocol, Set, Type, Union
import warnings


class ConfigScope(str, Enum):
    """Configuration scopes for organizing settings."""
    CORE = "core"           # Core SDK settings
    LLM = "llm"            # LLM provider settings  
    MEMORY = "memory"       # Memory and persistence
    TOOLS = "tools"        # Tool configurations
    BOTS = "bots"          # Bot platform settings
    GATEWAY = "gateway"    # Gateway server settings
    INTEGRATIONS = "integrations"  # External integrations


class ConfigType(str, Enum):
    """Configuration value types for validation."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    PATH = "path"
    URL = "url"


@dataclass
class ConfigEntry:
    """Configuration entry with metadata."""
    key: str
    scope: ConfigScope = ConfigScope.CORE
    type: ConfigType = ConfigType.STRING
    default: Any = None
    description: str = ""
    env_var: Optional[str] = None  # Override env var name if different from key
    deprecated: bool = False
    aliases: List[str] = field(default_factory=list)
    validation: Optional[callable] = None
    
    def __post_init__(self):
        """Set env_var to key if not provided."""
        if self.env_var is None:
            self.env_var = self.key


class ConfigProtocol(Protocol):
    """Protocol for configuration providers."""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        ...
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        ...
    
    @abstractmethod
    def has(self, key: str) -> bool:
        """Check if configuration key exists."""
        ...
    
    @abstractmethod
    def list_keys(self) -> List[str]:
        """List all available configuration keys."""
        ...


class EnvironmentConfigProvider:
    """Configuration provider that reads from environment variables."""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_enabled = True
    
    def get(self, key: str, default: Any = None, config_type: ConfigType = ConfigType.STRING) -> Any:
        """Get value from environment with type conversion and caching."""
        if self._cache_enabled and key in self._cache:
            return self._cache[key]
        
        env_value = os.getenv(key)
        if env_value is None:
            return default
        
        # Type conversion
        try:
            converted_value = self._convert_type(env_value, config_type)
            if self._cache_enabled:
                self._cache[key] = converted_value
            return converted_value
        except (ValueError, TypeError) as e:
            warnings.warn(f"Failed to convert env var {key}={env_value} to {config_type}: {e}")
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set environment variable and clear cache."""
        os.environ[key] = str(value)
        self._cache.pop(key, None)
    
    def has(self, key: str) -> bool:
        """Check if environment variable exists."""
        return key in os.environ
    
    def list_keys(self) -> List[str]:
        """List all environment variable keys."""
        return list(os.environ.keys())
    
    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._cache.clear()
    
    def disable_cache(self) -> None:
        """Disable caching (useful for testing)."""
        self._cache_enabled = False
        self._cache.clear()
    
    def enable_cache(self) -> None:
        """Enable caching."""
        self._cache_enabled = True
    
    def _convert_type(self, value: str, config_type: ConfigType) -> Any:
        """Convert string value to specified type."""
        if config_type == ConfigType.STRING:
            return value
        elif config_type == ConfigType.INTEGER:
            return int(value)
        elif config_type == ConfigType.FLOAT:
            return float(value)
        elif config_type == ConfigType.BOOLEAN:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif config_type == ConfigType.LIST:
            # Support comma-separated values
            return [item.strip() for item in value.split(',') if item.strip()]
        elif config_type == ConfigType.DICT:
            # Support JSON-like format (simplified)
            import json
            return json.loads(value)
        elif config_type in (ConfigType.PATH, ConfigType.URL):
            return value  # No conversion needed, but could add validation
        else:
            return value


class ConfigRegistry:
    """Central registry for all configuration entries."""
    
    _entries: Dict[str, ConfigEntry] = {}
    _aliases: Dict[str, str] = {}  # alias -> canonical key mapping
    _provider = EnvironmentConfigProvider()
    
    @classmethod
    def register(
        self,
        key: str,
        scope: ConfigScope = ConfigScope.CORE,
        type: ConfigType = ConfigType.STRING,
        default: Any = None,
        description: str = "",
        env_var: Optional[str] = None,
        deprecated: bool = False,
        aliases: Optional[List[str]] = None,
        validation: Optional[callable] = None,
    ) -> ConfigEntry:
        """Register a configuration entry."""
        entry = ConfigEntry(
            key=key,
            scope=scope,
            type=type,
            default=default,
            description=description,
            env_var=env_var,
            deprecated=deprecated,
            aliases=aliases or [],
            validation=validation,
        )
        
        self._entries[key] = entry
        
        # Register aliases
        for alias in entry.aliases:
            self._aliases[alias] = key
        
        return entry
    
    @classmethod
    def get_entry(cls, key: str) -> Optional[ConfigEntry]:
        """Get configuration entry by key or alias."""
        # Check direct key first
        if key in cls._entries:
            return cls._entries[key]
        
        # Check aliases
        canonical_key = cls._aliases.get(key)
        if canonical_key:
            return cls._entries[canonical_key]
        
        return None
    
    @classmethod
    def list_entries(cls, scope: Optional[ConfigScope] = None) -> List[ConfigEntry]:
        """List all registered configuration entries."""
        entries = list(cls._entries.values())
        if scope:
            entries = [e for e in entries if e.scope == scope]
        return entries
    
    @classmethod
    def get_unknown_env_vars(cls) -> Set[str]:
        """Get environment variables that are not registered."""
        all_env_vars = set(os.environ.keys())
        registered_vars = {entry.env_var for entry in cls._entries.values()}
        
        # Filter out common system env vars
        system_vars = {
            'PATH', 'HOME', 'USER', 'SHELL', 'PWD', 'OLDPWD', 'TERM', 'LANG',
            'LC_ALL', 'TZ', 'TMPDIR', 'PYTHONPATH', 'VIRTUAL_ENV', 'CONDA_PREFIX'
        }
        
        unknown_vars = all_env_vars - registered_vars - system_vars
        
        # Filter PraisonAI-related vars only (to reduce noise)
        praison_vars = {var for var in unknown_vars if 'PRAISON' in var or any(
            provider in var for provider in ['OPENAI', 'ANTHROPIC', 'GOOGLE', 'GEMINI', 'CLAUDE']
        )}
        
        return praison_vars
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered entries (for testing)."""
        cls._entries.clear()
        cls._aliases.clear()
        cls._provider.clear_cache()


# Main configuration access functions

def get_config(key: str, default: Any = None, type: ConfigType = ConfigType.STRING) -> Any:
    """
    Get configuration value with unified resolution.
    
    Resolution order:
    1. Registered configuration entry (with type conversion)
    2. Direct environment variable lookup
    3. Default value
    
    Args:
        key: Configuration key or environment variable name
        default: Default value if not found
        type: Expected configuration type for conversion
    
    Returns:
        Configuration value with appropriate type conversion
    """
    # Check if this is a registered configuration
    entry = ConfigRegistry.get_entry(key)
    if entry:
        if entry.deprecated:
            warnings.warn(f"Configuration {key} is deprecated: {entry.description}")
        
        value = ConfigRegistry._provider.get(
            entry.env_var, 
            default=entry.default if default is None else default,
            config_type=entry.type
        )
        
        # Apply validation if provided
        if entry.validation and value is not None:
            try:
                entry.validation(value)
            except Exception as e:
                warnings.warn(f"Validation failed for {key}={value}: {e}")
        
        return value
    
    # Fall back to direct environment variable lookup (backward compatibility)
    return ConfigRegistry._provider.get(key, default=default, config_type=type)


def set_config(key: str, value: Any) -> None:
    """Set configuration value."""
    entry = ConfigRegistry.get_entry(key)
    env_var = entry.env_var if entry else key
    ConfigRegistry._provider.set(env_var, value)


def has_config(key: str) -> bool:
    """Check if configuration key exists."""
    entry = ConfigRegistry.get_entry(key)
    env_var = entry.env_var if entry else key
    return ConfigRegistry._provider.has(env_var)


def list_config_keys() -> List[str]:
    """List all registered configuration keys."""
    return list(ConfigRegistry._entries.keys())


def validate_config() -> Dict[str, List[str]]:
    """
    Validate current configuration and return warnings.
    
    Returns:
        Dictionary with validation results:
        - "unknown_vars": Unknown environment variables
        - "deprecated_vars": Deprecated configuration in use
        - "validation_errors": Configuration values that failed validation
    """
    results = {
        "unknown_vars": [],
        "deprecated_vars": [],
        "validation_errors": []
    }
    
    # Check for unknown variables
    unknown_vars = ConfigRegistry.get_unknown_env_vars()
    results["unknown_vars"] = sorted(unknown_vars)
    
    # Check for deprecated vars in use
    for entry in ConfigRegistry.list_entries():
        if entry.deprecated and ConfigRegistry._provider.has(entry.env_var):
            results["deprecated_vars"].append(entry.key)
    
    # Check validation errors
    for entry in ConfigRegistry.list_entries():
        if entry.validation and ConfigRegistry._provider.has(entry.env_var):
            try:
                value = get_config(entry.key)
                entry.validation(value)
            except Exception as e:
                results["validation_errors"].append(f"{entry.key}: {e}")
    
    return results


# Register core PraisonAI configuration entries
def _register_core_configs():
    """Register core configuration entries."""
    # LLM Provider Settings
    ConfigRegistry.register(
        "OPENAI_API_KEY",
        scope=ConfigScope.LLM,
        type=ConfigType.STRING,
        description="OpenAI API key for GPT models"
    )
    
    ConfigRegistry.register(
        "OPENAI_BASE_URL", 
        scope=ConfigScope.LLM,
        type=ConfigType.URL,
        aliases=["OPENAI_API_BASE"],
        description="OpenAI API base URL"
    )
    
    ConfigRegistry.register(
        "ANTHROPIC_API_KEY",
        scope=ConfigScope.LLM, 
        type=ConfigType.STRING,
        aliases=["CLAUDE_API_KEY"],
        description="Anthropic API key for Claude models"
    )
    
    ConfigRegistry.register(
        "GOOGLE_API_KEY",
        scope=ConfigScope.LLM,
        type=ConfigType.STRING, 
        aliases=["GEMINI_API_KEY"],
        description="Google API key for Gemini models"
    )
    
    # Memory Configuration
    ConfigRegistry.register(
        "PRAISONAI_MEMORY_BACKEND",
        scope=ConfigScope.MEMORY,
        type=ConfigType.STRING,
        default="file",
        description="Memory storage backend (file, sqlite, redis, postgres)"
    )
    
    # Bot Platform Tokens
    ConfigRegistry.register(
        "TELEGRAM_BOT_TOKEN",
        scope=ConfigScope.BOTS,
        type=ConfigType.STRING,
        description="Telegram bot token"
    )
    
    ConfigRegistry.register(
        "DISCORD_BOT_TOKEN", 
        scope=ConfigScope.BOTS,
        type=ConfigType.STRING,
        description="Discord bot token"
    )
    
    # Logging and Debug
    ConfigRegistry.register(
        "LITELLM_TELEMETRY",
        scope=ConfigScope.CORE,
        type=ConfigType.BOOLEAN,
        default=False,
        description="Enable LiteLLM telemetry"
    )
    
    ConfigRegistry.register(
        "PRAISONAI_DEBUG",
        scope=ConfigScope.CORE,
        type=ConfigType.BOOLEAN,
        default=False,
        description="Enable debug logging"
    )


# Initialize core configurations
_register_core_configs()


# Backward compatibility functions - these maintain existing behavior
# while routing through the new unified system

@lru_cache(maxsize=256)
def getenv_cached(key: str, default: Any = None) -> Any:
    """Backward compatible cached getenv function."""
    return get_config(key, default)


def clear_env_cache() -> None:
    """Clear the environment variable cache."""
    getenv_cached.cache_clear()
    ConfigRegistry._provider.clear_cache()