"""
Configuration paths for PraisonAI CLI.

Defines standard locations for configuration files.
"""

import os
from pathlib import Path
from typing import List, Optional


def get_user_config_dir() -> Path:
    """Get user configuration directory (~/.praison/)."""
    return Path.home() / ".praison"


def get_user_config_path() -> Path:
    """Get user configuration file path (~/.praison/config.toml)."""
    return get_user_config_dir() / "config.toml"


def get_project_config_dir(project_root: Optional[Path] = None) -> Path:
    """Get project configuration directory (.praison/)."""
    root = project_root or Path.cwd()
    return root / ".praison"


def get_project_config_path(project_root: Optional[Path] = None) -> Path:
    """Get project configuration file path (.praison/config.toml)."""
    return get_project_config_dir(project_root) / "config.toml"


def get_sessions_dir() -> Path:
    """Get sessions directory (~/.praison/sessions/)."""
    return get_user_config_dir() / "sessions"


def get_traces_dir() -> Path:
    """Get traces directory (~/.praison/traces/)."""
    return get_user_config_dir() / "traces"


def get_logs_dir() -> Path:
    """Get logs directory (~/.praison/logs/)."""
    return get_user_config_dir() / "logs"


def get_cache_dir() -> Path:
    """Get cache directory (~/.praison/cache/)."""
    return get_user_config_dir() / "cache"


def get_config_paths(project_root: Optional[Path] = None) -> List[Path]:
    """
    Get all configuration file paths in precedence order (highest first).
    
    Precedence:
    1. Project config: .praison/config.toml
    2. User config: ~/.praison/config.toml
    
    Returns:
        List of paths in precedence order
    """
    paths = []
    
    # Project config (highest precedence)
    project_config = get_project_config_path(project_root)
    if project_config.exists():
        paths.append(project_config)
    
    # User config
    user_config = get_user_config_path()
    if user_config.exists():
        paths.append(user_config)
    
    return paths


def ensure_config_dirs() -> None:
    """Ensure all configuration directories exist."""
    dirs = [
        get_user_config_dir(),
        get_sessions_dir(),
        get_traces_dir(),
        get_logs_dir(),
        get_cache_dir(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def get_env_prefix() -> str:
    """Get environment variable prefix."""
    return "PRAISONAI_"


def env_to_config_key(env_var: str) -> Optional[str]:
    """
    Convert environment variable name to config key.
    
    Example: PRAISONAI_OUTPUT_FORMAT -> output.format
    """
    prefix = get_env_prefix()
    if not env_var.startswith(prefix):
        return None
    
    key = env_var[len(prefix):].lower()
    # Convert underscores to dots for nested keys
    # Single underscore = dot, double underscore = single underscore
    parts = key.split("__")
    result_parts = []
    for part in parts:
        result_parts.append(part.replace("_", "."))
    return "_".join(result_parts)
