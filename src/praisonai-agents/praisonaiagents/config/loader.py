"""
Configuration Loader for PraisonAI Agents.

Loads configuration from multiple sources with precedence:
1. Explicit parameters (highest)
2. Environment variables
3. Config file (.praisonai/config.toml or praisonai.toml)
4. Defaults (lowest)

Zero Performance Impact:
- Config is loaded lazily on first access
- No file I/O at import time
- Cached after first load

Usage:
    from praisonaiagents.config.loader import get_config, get_default
    
    # Get entire config
    config = get_config()
    
    # Get specific default with fallback
    model = get_default("model", "gpt-4o-mini")
    memory_config = get_default("memory", {})
    
    # Validate config file
    errors = validate_config(config.to_dict())
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


# ============================================================================
# CONFIG VALIDATION SCHEMA
# ============================================================================
# Defines valid keys and types for config file validation

VALID_PLUGINS_KEYS = {
    "enabled": (bool, list, str),  # bool, list of plugin names, or "true"/"false"
    "auto_discover": (bool,),
    "directories": (list,),
}

VALID_DEFAULTS_KEYS = {
    # LLM settings
    "model": (str,),
    "base_url": (str,),
    "api_key": (str,),
    # Feature flags
    "allow_delegation": (bool,),
    "allow_code_execution": (bool,),
    "code_execution_mode": (str,),
    # Feature configs (nested dicts with 'enabled' key)
    "memory": (dict, bool),
    "knowledge": (dict, bool),
    "planning": (dict, bool),
    "reflection": (dict, bool),
    "guardrails": (dict, bool),
    "web": (dict, bool),
    "output": (dict, str),  # dict or preset string
    "execution": (dict, str),  # dict or preset string
    "caching": (dict, bool),
    "autonomy": (dict, bool),
    "skills": (dict, list),
    "context": (dict, bool),
    "hooks": (dict, list),
    "templates": (dict,),
}

VALID_ROOT_KEYS = {"plugins", "defaults"}


class ConfigValidationError(Exception):
    """Raised when config file has validation errors."""
    
    def __init__(self, errors: List[str]):
        self.errors = errors
        message = "Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)

# Global config cache (lazy loaded)
_config_cache: Optional[Dict[str, Any]] = None
_config_loaded: bool = False


@dataclass
class PluginsConfig:
    """Configuration for the plugin system."""
    enabled: Union[bool, List[str]] = False  # True, False, or list of plugin names
    auto_discover: bool = True
    directories: List[str] = field(default_factory=lambda: [
        "./.praisonai/plugins/",
        "~/.praisonai/plugins/"
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "auto_discover": self.auto_discover,
            "directories": self.directories,
        }


@dataclass  
class DefaultsConfig:
    """Default configuration for Agent parameters."""
    # LLM defaults
    model: Optional[str] = None
    base_url: Optional[str] = None
    
    # Feature flags
    allow_delegation: bool = False
    allow_code_execution: bool = False
    code_execution_mode: str = "safe"
    
    # Feature configs (nested dicts)
    memory: Optional[Dict[str, Any]] = None
    knowledge: Optional[Dict[str, Any]] = None
    planning: Optional[Dict[str, Any]] = None
    reflection: Optional[Dict[str, Any]] = None
    web: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None
    caching: Optional[Dict[str, Any]] = None
    autonomy: Optional[Dict[str, Any]] = None
    skills: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "allow_delegation": self.allow_delegation,
            "allow_code_execution": self.allow_code_execution,
            "code_execution_mode": self.code_execution_mode,
            "memory": self.memory,
            "knowledge": self.knowledge,
            "planning": self.planning,
            "reflection": self.reflection,
            "web": self.web,
            "output": self.output,
            "execution": self.execution,
            "caching": self.caching,
            "autonomy": self.autonomy,
            "skills": self.skills,
        }


@dataclass
class PraisonConfig:
    """Root configuration for PraisonAI Agents."""
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugins": self.plugins.to_dict(),
            "defaults": self.defaults.to_dict(),
        }


def _find_config_file() -> Optional[Path]:
    """Find config file in standard locations.
    
    Search order:
    1. .praisonai/config.toml (project-local)
    2. praisonai.toml (project root)
    3. ~/.praisonai/config.toml (user global)
    
    Returns:
        Path to config file if found, None otherwise
    """
    # Project-local locations
    cwd = Path.cwd()
    local_paths = [
        cwd / ".praisonai" / "config.toml",
        cwd / "praisonai.toml",
    ]
    
    for path in local_paths:
        if path.exists():
            return path
    
    # User global location
    home = Path.home()
    global_path = home / ".praisonai" / "config.toml"
    if global_path.exists():
        return global_path
    
    return None


def _parse_toml(path: Path) -> Dict[str, Any]:
    """Parse TOML file with fallback for Python < 3.11.
    
    Args:
        path: Path to TOML file
        
    Returns:
        Parsed config dict
    """
    try:
        # Python 3.11+ has built-in tomllib
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        # Fallback for Python < 3.11
        try:
            import tomli
            with open(path, "rb") as f:
                return tomli.load(f)
        except ImportError:
            # No TOML parser available - return empty config
            import logging
            logging.debug(
                "TOML parser not available. Install tomli for Python < 3.11: "
                "pip install tomli"
            )
            return {}


def _load_config() -> Dict[str, Any]:
    """Load configuration from file.
    
    Returns:
        Config dict (empty if no config file found)
    """
    config_path = _find_config_file()
    if config_path is None:
        return {}
    
    try:
        return _parse_toml(config_path)
    except Exception as e:
        import logging
        logging.warning(f"Failed to load config from {config_path}: {e}")
        return {}


def _dict_to_plugins_config(data: Dict[str, Any]) -> PluginsConfig:
    """Convert dict to PluginsConfig."""
    return PluginsConfig(
        enabled=data.get("enabled", False),
        auto_discover=data.get("auto_discover", True),
        directories=data.get("directories", [
            "./.praisonai/plugins/",
            "~/.praisonai/plugins/"
        ]),
    )


def _dict_to_defaults_config(data: Dict[str, Any]) -> DefaultsConfig:
    """Convert dict to DefaultsConfig."""
    return DefaultsConfig(
        model=data.get("model"),
        base_url=data.get("base_url"),
        allow_delegation=data.get("allow_delegation", False),
        allow_code_execution=data.get("allow_code_execution", False),
        code_execution_mode=data.get("code_execution_mode", "safe"),
        memory=data.get("memory"),
        knowledge=data.get("knowledge"),
        planning=data.get("planning"),
        reflection=data.get("reflection"),
        web=data.get("web"),
        output=data.get("output"),
        execution=data.get("execution"),
        caching=data.get("caching"),
        autonomy=data.get("autonomy"),
        skills=data.get("skills"),
    )


def _dict_to_praison_config(data: Dict[str, Any]) -> PraisonConfig:
    """Convert dict to PraisonConfig."""
    plugins_data = data.get("plugins", {})
    defaults_data = data.get("defaults", {})
    
    return PraisonConfig(
        plugins=_dict_to_plugins_config(plugins_data),
        defaults=_dict_to_defaults_config(defaults_data),
    )


def get_config(reload: bool = False) -> PraisonConfig:
    """Get the global configuration.
    
    Loads config lazily on first access and caches it.
    
    Args:
        reload: Force reload from file
        
    Returns:
        PraisonConfig instance
    """
    global _config_cache, _config_loaded
    
    if not _config_loaded or reload:
        raw_config = _load_config()
        _config_cache = _dict_to_praison_config(raw_config)
        _config_loaded = True
    
    return _config_cache


def get_plugins_config() -> PluginsConfig:
    """Get plugins configuration.
    
    Returns:
        PluginsConfig instance
    """
    return get_config().plugins


def get_defaults_config() -> DefaultsConfig:
    """Get defaults configuration.
    
    Returns:
        DefaultsConfig instance
    """
    return get_config().defaults


def get_default(key: str, fallback: Any = None) -> Any:
    """Get a specific default value.
    
    Args:
        key: Config key (e.g., "model", "memory", "memory.backend")
        fallback: Value to return if key not found
        
    Returns:
        Config value or fallback
    """
    defaults = get_defaults_config()
    
    # Handle nested keys like "memory.backend"
    if "." in key:
        parts = key.split(".")
        value = getattr(defaults, parts[0], None)
        if value is None:
            return fallback
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return fallback
            if value is None:
                return fallback
        return value
    
    # Simple key
    value = getattr(defaults, key, None)
    return value if value is not None else fallback


def is_plugins_enabled() -> bool:
    """Check if plugins are enabled via config or env var.
    
    Returns:
        True if plugins should be enabled
    """
    # Check env var first (highest precedence)
    env_value = os.environ.get("PRAISONAI_PLUGINS", "").lower()
    if env_value:
        if env_value in ("true", "1", "yes", "on"):
            return True
        if env_value in ("false", "0", "no", "off"):
            return False
        # Treat as comma-separated list of plugin names
        return True
    
    # Check config file
    plugins_config = get_plugins_config()
    if isinstance(plugins_config.enabled, bool):
        return plugins_config.enabled
    if isinstance(plugins_config.enabled, list):
        return len(plugins_config.enabled) > 0
    
    return False


def get_enabled_plugins() -> Optional[List[str]]:
    """Get list of enabled plugins (if specific list provided).
    
    Returns:
        List of plugin names, or None if all plugins enabled
    """
    # Check env var first
    env_value = os.environ.get("PRAISONAI_PLUGINS", "").lower()
    if env_value and env_value not in ("true", "1", "yes", "on", "false", "0", "no", "off"):
        # Treat as comma-separated list
        return [p.strip() for p in env_value.split(",") if p.strip()]
    
    # Check config file
    plugins_config = get_plugins_config()
    if isinstance(plugins_config.enabled, list):
        return plugins_config.enabled
    
    return None  # All plugins enabled


def clear_config_cache() -> None:
    """Clear the config cache (for testing)."""
    global _config_cache, _config_loaded
    _config_cache = None
    _config_loaded = False


def validate_config(config: Dict[str, Any], raise_on_error: bool = False) -> List[str]:
    """Validate config file structure and types.
    
    Args:
        config: Raw config dict (from TOML parsing)
        raise_on_error: If True, raise ConfigValidationError on errors
        
    Returns:
        List of validation error messages (empty if valid)
        
    Example:
        config = {"plugins": {"enabled": True}, "defaults": {"model": "gpt-4o"}}
        errors = validate_config(config)
        if errors:
            print("Config errors:", errors)
    """
    errors = []
    
    # Check root keys
    for key in config.keys():
        if key not in VALID_ROOT_KEYS:
            similar = _suggest_similar_key(key, VALID_ROOT_KEYS)
            if similar:
                errors.append(f"Unknown root key '{key}'. Did you mean '{similar}'?")
            else:
                errors.append(f"Unknown root key '{key}'. Valid keys: {', '.join(sorted(VALID_ROOT_KEYS))}")
    
    # Validate [plugins] section
    if "plugins" in config:
        plugins = config["plugins"]
        if not isinstance(plugins, dict):
            errors.append(f"[plugins] must be a table, got {type(plugins).__name__}")
        else:
            for key, value in plugins.items():
                if key not in VALID_PLUGINS_KEYS:
                    similar = _suggest_similar_key(key, VALID_PLUGINS_KEYS.keys())
                    if similar:
                        errors.append(f"[plugins] Unknown key '{key}'. Did you mean '{similar}'?")
                    else:
                        errors.append(f"[plugins] Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_PLUGINS_KEYS.keys()))}")
                else:
                    valid_types = VALID_PLUGINS_KEYS[key]
                    if not isinstance(value, valid_types):
                        errors.append(f"[plugins.{key}] Expected {_format_types(valid_types)}, got {type(value).__name__}")
    
    # Validate [defaults] section
    if "defaults" in config:
        defaults = config["defaults"]
        if not isinstance(defaults, dict):
            errors.append(f"[defaults] must be a table, got {type(defaults).__name__}")
        else:
            for key, value in defaults.items():
                if key not in VALID_DEFAULTS_KEYS:
                    similar = _suggest_similar_key(key, VALID_DEFAULTS_KEYS.keys())
                    if similar:
                        errors.append(f"[defaults] Unknown key '{key}'. Did you mean '{similar}'?")
                    else:
                        errors.append(f"[defaults] Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_DEFAULTS_KEYS.keys()))}")
                else:
                    valid_types = VALID_DEFAULTS_KEYS[key]
                    if not isinstance(value, valid_types):
                        errors.append(f"[defaults.{key}] Expected {_format_types(valid_types)}, got {type(value).__name__}")
                    # Validate nested feature configs
                    if isinstance(value, dict) and key in ("memory", "knowledge", "planning", "reflection", 
                                                           "guardrails", "web", "output", "execution", 
                                                           "caching", "autonomy", "context"):
                        nested_errors = _validate_feature_config(key, value)
                        errors.extend(nested_errors)
    
    if raise_on_error and errors:
        raise ConfigValidationError(errors)
    
    return errors


def _suggest_similar_key(key: str, valid_keys) -> Optional[str]:
    """Suggest a similar valid key using simple string matching."""
    key_lower = key.lower()
    for valid in valid_keys:
        # Exact match after lowercasing
        if valid.lower() == key_lower:
            return valid
        # Prefix match
        if valid.lower().startswith(key_lower) or key_lower.startswith(valid.lower()):
            return valid
        # Substring match
        if key_lower in valid.lower() or valid.lower() in key_lower:
            return valid
    return None


def _format_types(types: tuple) -> str:
    """Format type tuple for error messages."""
    type_names = []
    for t in types:
        if t is bool:
            type_names.append("bool")
        elif t is str:
            type_names.append("str")
        elif t is dict:
            type_names.append("table")
        elif t is list:
            type_names.append("array")
        else:
            type_names.append(t.__name__)
    return " or ".join(type_names)


def _validate_feature_config(feature: str, config: Dict[str, Any]) -> List[str]:
    """Validate a nested feature config (memory, knowledge, etc.)."""
    errors = []
    
    # Common valid keys for feature configs
    common_keys = {"enabled", "backend", "provider", "preset", "verbose"}
    
    # Feature-specific valid keys
    feature_keys = {
        "memory": {"enabled", "backend", "provider", "use_long_term", "use_short_term", 
                   "user_id", "session_id", "db_path", "collection_name"},
        "knowledge": {"enabled", "sources", "provider", "chunk_size", "chunk_overlap"},
        "planning": {"enabled", "max_steps", "reasoning"},
        "reflection": {"enabled", "max_reflect", "min_reflect", "llm"},
        "guardrails": {"enabled", "max_retries", "validator"},
        "web": {"enabled", "search", "fetch", "provider"},
        "output": {"enabled", "verbose", "markdown", "stream", "metrics", "preset"},
        "execution": {"enabled", "max_iter", "max_rpm", "max_execution_time", "preset"},
        "caching": {"enabled", "prompt_caching", "ttl"},
        "autonomy": {"enabled", "max_steps", "approval_required"},
        "context": {"enabled", "max_tokens", "strategy"},
    }
    
    valid_keys = feature_keys.get(feature, common_keys)
    
    for key in config.keys():
        if key not in valid_keys:
            similar = _suggest_similar_key(key, valid_keys)
            if similar:
                errors.append(f"[defaults.{feature}.{key}] Unknown key. Did you mean '{similar}'?")
            # Don't error on unknown nested keys - allow flexibility
    
    return errors


def get_config_path() -> Optional[Path]:
    """Get the path to the config file if it exists.
    
    Returns:
        Path to config file, or None if not found
    """
    return _find_config_file()


# Convenience function to merge config defaults with explicit params
def apply_config_defaults(
    param_name: str,
    explicit_value: Any,
    config_class: Optional[type] = None,
) -> Any:
    """Apply config defaults to a parameter if not explicitly set.
    
    Args:
        param_name: Name of the parameter (e.g., "memory", "knowledge")
        explicit_value: Value explicitly passed by user (None if not set)
        config_class: Optional config class to instantiate
        
    Returns:
        Resolved value with config defaults applied
        
    Example:
        # User passes memory=True, config has memory.backend="postgres"
        # Result: MemoryConfig with backend="postgres"
        
        memory = apply_config_defaults("memory", True, MemoryConfig)
    """
    # If user explicitly passed a value, respect it
    if explicit_value is not None:
        # If True and we have config defaults, merge them
        if explicit_value is True:
            config_defaults = get_default(param_name)
            if config_defaults and isinstance(config_defaults, dict):
                if config_class:
                    # Check if enabled key exists and is True
                    if config_defaults.get("enabled", True):
                        return config_class(**{k: v for k, v in config_defaults.items() if k != "enabled"})
                return config_defaults
        return explicit_value
    
    # Check if config has defaults for this param
    config_defaults = get_default(param_name)
    if config_defaults is None:
        return None
    
    # If config has enabled=True, return the config
    if isinstance(config_defaults, dict):
        if config_defaults.get("enabled", False):
            if config_class:
                return config_class(**{k: v for k, v in config_defaults.items() if k != "enabled"})
            return True
    
    return None
