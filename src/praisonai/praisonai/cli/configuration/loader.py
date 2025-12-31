"""
Configuration loader for PraisonAI CLI.

Handles loading, merging, and saving configuration with precedence.
"""

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import (
    get_config_paths,
    get_user_config_path,
    get_project_config_path,
    get_env_prefix,
    ensure_config_dirs,
)
from .schema import ConfigSchema, DEFAULT_CONFIG


# Thread-safe config cache
_config_lock = threading.Lock()
_config_cache: Optional[ConfigSchema] = None


def _load_toml(path: Path) -> Dict[str, Any]:
    """Load a TOML file."""
    try:
        # Try tomllib (Python 3.11+) first
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass
    
    try:
        # Fall back to tomli
        import tomli
        with open(path, "rb") as f:
            return tomli.load(f)
    except ImportError:
        pass
    
    # Last resort: basic TOML parsing
    return _basic_toml_parse(path)


def _basic_toml_parse(path: Path) -> Dict[str, Any]:
    """Basic TOML parser for simple configs."""
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                if current_section not in result:
                    result[current_section] = {}
            elif "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # Parse value
                if value.lower() == "true":
                    parsed_value = True
                elif value.lower() == "false":
                    parsed_value = False
                elif value.startswith('"') and value.endswith('"'):
                    parsed_value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    parsed_value = value[1:-1]
                else:
                    try:
                        parsed_value = int(value)
                    except ValueError:
                        try:
                            parsed_value = float(value)
                        except ValueError:
                            parsed_value = value
                
                if current_section:
                    result[current_section][key] = parsed_value
                else:
                    result[key] = parsed_value
    
    return result


def _save_toml(path: Path, data: Dict[str, Any]) -> None:
    """Save data to a TOML file."""
    try:
        import tomli_w
        with open(path, "wb") as f:
            tomli_w.dump(data, f)
        return
    except ImportError:
        pass
    
    # Fall back to basic TOML writing
    _basic_toml_write(path, data)


def _basic_toml_write(path: Path, data: Dict[str, Any]) -> None:
    """Basic TOML writer."""
    lines = []
    
    # Write top-level keys first
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_format_toml_value(value)}")
    
    # Write sections
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"\n[{key}]")
            for sub_key, sub_value in value.items():
                if not isinstance(sub_value, dict):
                    lines.append(f"{sub_key} = {_format_toml_value(sub_value)}")
                else:
                    # Nested section
                    lines.append(f"\n[{key}.{sub_key}]")
                    for nested_key, nested_value in sub_value.items():
                        lines.append(f"{nested_key} = {_format_toml_value(nested_value)}")
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _format_toml_value(value: Any) -> str:
    """Format a value for TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = ", ".join(_format_toml_value(v) for v in value)
        return f"[{items}]"
    else:
        return f'"{value}"'


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _get_env_overrides() -> Dict[str, Any]:
    """Get configuration overrides from environment variables."""
    prefix = get_env_prefix()
    overrides: Dict[str, Any] = {}
    
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        
        # Convert PRAISONAI_OUTPUT_FORMAT to output.format
        config_key = key[len(prefix):].lower()
        parts = config_key.split("_")
        
        # Parse value
        if value.lower() == "true":
            parsed_value = True
        elif value.lower() == "false":
            parsed_value = False
        else:
            try:
                parsed_value = int(value)
            except ValueError:
                try:
                    parsed_value = float(value)
                except ValueError:
                    parsed_value = value
        
        # Build nested dict
        if len(parts) >= 2:
            section = parts[0]
            sub_key = "_".join(parts[1:])
            if section not in overrides:
                overrides[section] = {}
            overrides[section][sub_key] = parsed_value
        else:
            overrides[config_key] = parsed_value
    
    return overrides


def _get_dotted_value(data: Dict[str, Any], key: str) -> Any:
    """Get a value using dotted key notation."""
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _set_dotted_value(data: Dict[str, Any], key: str, value: Any) -> None:
    """Set a value using dotted key notation."""
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


class ConfigLoader:
    """
    Configuration loader with precedence handling.
    
    Precedence (highest to lowest):
    1. CLI flags (not handled here)
    2. Environment variables (PRAISONAI_*)
    3. Project config (.praison/config.toml)
    4. User config (~/.praison/config.toml)
    5. Defaults
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self._config: Optional[ConfigSchema] = None
        self._raw_config: Dict[str, Any] = {}
    
    def load(self, force_reload: bool = False) -> ConfigSchema:
        """Load configuration with precedence."""
        if self._config is not None and not force_reload:
            return self._config
        
        # Start with defaults
        merged = DEFAULT_CONFIG.to_dict()
        
        # Load config files in reverse precedence order
        config_paths = get_config_paths(self.project_root)
        for path in reversed(config_paths):
            try:
                file_config = _load_toml(path)
                merged = _merge_dicts(merged, file_config)
            except Exception:
                pass  # Skip invalid files
        
        # Apply environment overrides
        env_overrides = _get_env_overrides()
        merged = _merge_dicts(merged, env_overrides)
        
        self._raw_config = merged
        self._config = ConfigSchema.from_dict(merged)
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dotted key notation."""
        self.load()
        value = _get_dotted_value(self._raw_config, key)
        return value if value is not None else default
    
    def set(self, key: str, value: Any, scope: str = "user") -> None:
        """
        Set a configuration value.
        
        Args:
            key: Dotted key notation (e.g., "output.format")
            value: Value to set
            scope: "user" or "project"
        """
        if scope == "project":
            config_path = get_project_config_path(self.project_root)
        else:
            config_path = get_user_config_path()
        
        # Load existing config or create empty
        if config_path.exists():
            try:
                existing = _load_toml(config_path)
            except Exception:
                existing = {}
        else:
            existing = {}
        
        # Set the value
        _set_dotted_value(existing, key, value)
        
        # Ensure directory exists
        ensure_config_dirs()
        if scope == "project":
            config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save
        _save_toml(config_path, existing)
        
        # Reload
        self.load(force_reload=True)
    
    def reset(self, scope: str = "user") -> None:
        """Reset configuration to defaults."""
        if scope == "project":
            config_path = get_project_config_path(self.project_root)
        else:
            config_path = get_user_config_path()
        
        if config_path.exists():
            config_path.unlink()
        
        self.load(force_reload=True)
    
    def list_all(self) -> Dict[str, Any]:
        """List all configuration values."""
        self.load()
        return self._raw_config.copy()


# Global config loader
_global_loader: Optional[ConfigLoader] = None


def get_config(project_root: Optional[Path] = None) -> ConfigSchema:
    """Get the global configuration."""
    global _global_loader, _config_cache
    
    with _config_lock:
        if _global_loader is None or project_root is not None:
            _global_loader = ConfigLoader(project_root)
        
        if _config_cache is None:
            _config_cache = _global_loader.load()
        
        return _config_cache


def get_config_loader(project_root: Optional[Path] = None) -> ConfigLoader:
    """Get the global config loader."""
    global _global_loader
    
    with _config_lock:
        if _global_loader is None or project_root is not None:
            _global_loader = ConfigLoader(project_root)
        return _global_loader
