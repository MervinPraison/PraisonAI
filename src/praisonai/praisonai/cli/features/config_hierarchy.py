"""
Hierarchical Configuration System for PraisonAI CLI.

Provides project → user → global config precedence with JSON schema validation.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Config file names in order of precedence (highest first)
CONFIG_FILES = [
    ".praison.json",      # Project-local (hidden)
    "praison.json",       # Project-local (visible)
]

USER_CONFIG_PATH = "~/.config/praison/praison.json"
GLOBAL_CONFIG_PATH = "/etc/praison/praison.json"


class ConfigValidationError(Exception):
    """Raised when config validation fails."""
    pass


@dataclass
class ConfigSource:
    """Represents a configuration source."""
    path: str
    level: str  # "project", "user", "global"
    data: Dict[str, Any]


# JSON Schema for configuration validation
CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1},
        "providers": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "base_url": {"type": "string"},
                    "model": {"type": "string"},
                }
            }
        },
        "mcp": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "env": {"type": "object"},
                    "disabled_tools": {"type": "array", "items": {"type": "string"}},
                }
            }
        },
        "permissions": {
            "type": "object",
            "properties": {
                "allowed_tools": {"type": "array", "items": {"type": "string"}},
                "allowed_paths": {"type": "array", "items": {"type": "string"}},
                "auto_approve": {"type": "boolean"},
            }
        },
        "lsp": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                }
            }
        },
        "output": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["compact", "verbose", "quiet"]},
                "color": {"type": "boolean"},
            }
        },
        "attribution": {
            "type": "object",
            "properties": {
                "style": {"type": "string", "enum": ["assisted-by", "co-authored-by", "none"]},
                "include_model": {"type": "boolean"},
            }
        },
    }
}


def validate_config(config: Dict[str, Any], schema: Dict = CONFIG_SCHEMA) -> List[str]:
    """
    Validate config against schema. Returns list of validation errors.
    
    Simple validation without external dependencies.
    """
    errors = []
    
    def validate_value(value: Any, schema_part: Dict, path: str) -> None:
        expected_type = schema_part.get("type")
        
        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"{path}: expected number, got {type(value).__name__}")
        elif expected_type == "integer" and not isinstance(value, int):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")
        elif expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"{path}: expected boolean, got {type(value).__name__}")
        elif expected_type == "array" and not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
        elif expected_type == "object" and not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
        
        # Check enum
        if "enum" in schema_part and value not in schema_part["enum"]:
            errors.append(f"{path}: value must be one of {schema_part['enum']}")
        
        # Check minimum/maximum for numbers
        if isinstance(value, (int, float)):
            if "minimum" in schema_part and value < schema_part["minimum"]:
                errors.append(f"{path}: value must be >= {schema_part['minimum']}")
            if "maximum" in schema_part and value > schema_part["maximum"]:
                errors.append(f"{path}: value must be <= {schema_part['maximum']}")
    
    # Validate top-level properties
    properties = schema.get("properties", {})
    for key, value in config.items():
        if key in properties:
            validate_value(value, properties[key], key)
    
    return errors


class HierarchicalConfig:
    """
    Hierarchical configuration manager.
    
    Loads configuration from multiple sources with precedence:
    1. Project-level (.praison.json or praison.json in current dir)
    2. User-level (~/.config/praison/praison.json)
    3. Global-level (/etc/praison/praison.json)
    
    Higher precedence configs override lower ones.
    
    Usage:
        config = HierarchicalConfig()
        settings = config.load()
        
        # Access settings
        model = settings.get("model", "gpt-4o-mini")
    """
    
    def __init__(
        self,
        project_dir: Optional[str] = None,
        user_config: Optional[str] = None,
        global_config: Optional[str] = None,
    ):
        self.project_dir = project_dir or os.getcwd()
        self.user_config = os.path.expanduser(user_config or USER_CONFIG_PATH)
        self.global_config = global_config or GLOBAL_CONFIG_PATH
        self._sources: List[ConfigSource] = []
        self._merged: Dict[str, Any] = {}
    
    @property
    def precedence(self) -> List[str]:
        """Return config precedence order."""
        return ["project", "user", "global"]
    
    def _find_project_config(self) -> Optional[str]:
        """Find project-level config file."""
        for filename in CONFIG_FILES:
            path = os.path.join(self.project_dir, filename)
            if os.path.exists(path):
                return path
        return None
    
    def _load_json(self, path: str) -> Optional[Dict[str, Any]]:
        """Load JSON file, return None if not found or invalid."""
        if not os.path.exists(path):
            return None
        
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return None
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dicts, with override taking precedence."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def load(self, validate: bool = False) -> Dict[str, Any]:
        """
        Load and merge configuration from all sources.
        
        Args:
            validate: If True, validate config against schema
            
        Returns:
            Merged configuration dict
            
        Raises:
            ConfigValidationError: If validate=True and validation fails
        """
        self._sources = []
        self._merged = {}
        
        # Load in reverse precedence order (global first, project last)
        # Global config
        global_data = self._load_json(self.global_config)
        if global_data:
            self._sources.append(ConfigSource(
                path=self.global_config,
                level="global",
                data=global_data
            ))
            self._merged = self._deep_merge(self._merged, global_data)
        
        # User config
        user_data = self._load_json(self.user_config)
        if user_data:
            self._sources.append(ConfigSource(
                path=self.user_config,
                level="user",
                data=user_data
            ))
            self._merged = self._deep_merge(self._merged, user_data)
        
        # Project config
        project_path = self._find_project_config()
        if project_path:
            project_data = self._load_json(project_path)
            if project_data:
                self._sources.append(ConfigSource(
                    path=project_path,
                    level="project",
                    data=project_data
                ))
                self._merged = self._deep_merge(self._merged, project_data)
        
        # Validate if requested
        if validate:
            errors = validate_config(self._merged)
            if errors:
                raise ConfigValidationError(
                    f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                )
        
        return self._merged
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        if not self._merged:
            self.load()
        return self._merged.get(key, default)
    
    def get_sources(self) -> List[ConfigSource]:
        """Get list of loaded config sources."""
        return self._sources
    
    def save_user_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to user config file."""
        os.makedirs(os.path.dirname(self.user_config), exist_ok=True)
        with open(self.user_config, "w") as f:
            json.dump(config, f, indent=2)
    
    def save_project_config(self, config: Dict[str, Any], hidden: bool = True) -> None:
        """Save configuration to project config file."""
        filename = ".praison.json" if hidden else "praison.json"
        path = os.path.join(self.project_dir, filename)
        with open(path, "w") as f:
            json.dump(config, f, indent=2)


# Global config instance
_config: Optional[HierarchicalConfig] = None


def get_config() -> HierarchicalConfig:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = HierarchicalConfig()
    return _config


def load_config() -> Dict[str, Any]:
    """Load and return the merged configuration."""
    return get_config().load()
