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