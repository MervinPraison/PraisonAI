"""
Environment variable utilities for PraisonAI CLI.

Provides shared helpers for environment variable substitution
and loading .env files.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


def substitute_env_vars(value: Any) -> Any:
    """Substitute ${VAR} references with environment variable values.
    
    This is the canonical implementation for environment variable substitution
    used throughout PraisonAI configuration loading.
    
    Args:
        value: Value to substitute. Can be string, dict, list, or any type.
        
    Returns:
        Value with environment variables substituted.
        
    Examples:
        >>> os.environ['TOKEN'] = 'secret123'
        >>> substitute_env_vars('${TOKEN}')
        'secret123'
        >>> substitute_env_vars({'token': '${TOKEN}'})
        {'token': 'secret123'}
    """
    if isinstance(value, str):
        # Replace ${VAR} with os.environ.get(VAR, original)
        return re.sub(
            r'\$\{([^}]+)\}',
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value
        )
    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


# Matches {env:VAR} / {env:VAR:-default} and {file:./path} include directives.
_INTERPOLATION_PATTERN = re.compile(r'\{(env|file):([^}]+)\}')


def _resolve_directive(kind: str, arg: str, base_dir: Optional[Path]) -> str:
    """Resolve a single {env:...} or {file:...} directive to its string value."""
    if kind == "env":
        # Support {env:VAR} and {env:VAR:-default} (shell-style fallback).
        if ":-" in arg:
            name, default = arg.split(":-", 1)
        else:
            name, default = arg, ""
        return os.environ.get(name.strip(), default)

    # kind == "file": read the referenced file's contents (trailing newline
    # stripped), resolved relative to base_dir when the path is not absolute.
    raw_path = arg.strip()
    path = Path(os.path.expanduser(raw_path))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    try:
        return path.read_text().rstrip("\n")
    except OSError:
        # Leave the directive untouched when the file cannot be read so the
        # failure is visible rather than silently blanking a value.
        return "{file:" + arg + "}"


def interpolate(value: Any, base_dir: Optional[Path] = None) -> Any:
    """Interpolate ``${VAR}``, ``{env:VAR}`` and ``{file:./path}`` in a value.

    Applied uniformly across config/YAML surfaces so secrets and reused prompt
    text can live outside tracked config files. Recurses into dicts and lists.

    Args:
        value: Value to interpolate (string, dict, list, or any type).
        base_dir: Directory that ``{file:...}`` relative paths resolve against
            (typically the directory of the config file being loaded).

    Returns:
        Value with all supported directives resolved.

    Examples:
        >>> os.environ['TOKEN'] = 'secret123'
        >>> interpolate('{env:TOKEN}')
        'secret123'
        >>> interpolate('${TOKEN}')
        'secret123'
    """
    if isinstance(value, str):
        # First apply legacy ${VAR} substitution, then {env:}/{file:} directives.
        substituted = substitute_env_vars(value)
        return _INTERPOLATION_PATTERN.sub(
            lambda m: _resolve_directive(m.group(1), m.group(2), base_dir),
            substituted,
        )
    elif isinstance(value, dict):
        return {k: interpolate(v, base_dir) for k, v in value.items()}
    elif isinstance(value, list):
        return [interpolate(item, base_dir) for item in value]
    return value


def load_env_file(env_path: Optional[Path] = None, override: bool = False) -> Dict[str, str]:
    """Load environment variables from a .env file.
    
    Args:
        env_path: Path to .env file. Defaults to ~/.praisonai/.env
        override: If True, override existing environment variables
        
    Returns:
        Dictionary of loaded environment variables
    """
    if env_path is None:
        env_path = Path(os.environ.get("PRAISONAI_ENV_FILE") 
                       or (Path.home() / ".praisonai" / ".env"))
    
    loaded: Dict[str, str] = {}
    
    if not env_path.exists():
        return loaded
    
    try:
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
                
            # Parse KEY=VALUE
            if "=" not in line:
                continue
                
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            if not key:
                continue
            
            # Only set if override=True or not already in environment
            if override or key not in os.environ:
                os.environ[key] = value
                loaded[key] = value
                
    except OSError:
        # Silently fail if can't read file
        pass
    
    return loaded


def resolve_env_var(value: str) -> str:
    """Resolve a single environment variable reference.
    
    Args:
        value: String that may contain ${VAR} reference
        
    Returns:
        Resolved value
        
    Raises:
        ValueError: If environment variable is not set
    """
    if value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        resolved = os.environ.get(env_key)
        if not resolved:
            raise ValueError(
                f"Environment variable '{env_key}' not set. "
                f"Set it with: export {env_key}=your_value"
            )
        return resolved
    return value