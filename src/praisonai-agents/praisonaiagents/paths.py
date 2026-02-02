"""
Centralized Path Utilities for PraisonAI Agents.

All persistent data uses ~/.praisonai/ by default.
Override with PRAISONAI_HOME environment variable.

This module provides a single source of truth for all data storage paths,
eliminating hardcoded paths throughout the codebase (DRY principle).

Usage:
    from praisonaiagents.paths import get_data_dir, get_sessions_dir
    
    # Get user data directory
    data_dir = get_data_dir()  # ~/.praisonai/
    
    # Get specific subdirectories
    sessions_dir = get_sessions_dir()  # ~/.praisonai/sessions/
    
    # Override with environment variable
    # export PRAISONAI_HOME=/custom/path
    # data_dir = get_data_dir()  # /custom/path/

Backward Compatibility:
    If ~/.praisonai/ doesn't exist but ~/.praison/ does, the legacy
    path will be used with a deprecation warning. Run 'praisonai migrate-data'
    to migrate to the new location.
"""

import os
import warnings
from pathlib import Path
from typing import Dict, Optional, Union

# Environment variable for override
ENV_VAR = "PRAISONAI_HOME"

# Default directory name (branded)
DEFAULT_DIR_NAME = ".praisonai"

# Legacy directory name (for backward compat)
LEGACY_DIR_NAME = ".praison"

# Cache for data dir to avoid repeated filesystem checks
_data_dir_cache: Optional[Path] = None


def _clear_cache() -> None:
    """Clear the data dir cache. Used for testing."""
    global _data_dir_cache
    _data_dir_cache = None


def get_data_dir() -> Path:
    """
    Get PraisonAI data directory.
    
    Priority:
    1. PRAISONAI_HOME env var
    2. ~/.praisonai/ (default)
    3. ~/.praison/ (legacy fallback with warning)
    
    Returns:
        Path to data directory
    
    Example:
        >>> from praisonaiagents.paths import get_data_dir
        >>> data_dir = get_data_dir()
        >>> print(data_dir)
        /home/user/.praisonai
    """
    global _data_dir_cache
    
    # Check env var first (always takes precedence, no caching)
    env_path = os.environ.get(ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    
    # Return cached value if available
    if _data_dir_cache is not None:
        return _data_dir_cache
    
    home = Path.home()
    
    # Check new location first
    new_path = home / DEFAULT_DIR_NAME
    if new_path.exists():
        _data_dir_cache = new_path
        return new_path
    
    # Check legacy location (backward compat)
    legacy_path = home / LEGACY_DIR_NAME
    if legacy_path.exists():
        warnings.warn(
            f"Using legacy data directory {legacy_path}. "
            f"Run 'praisonai migrate-data' to migrate to {new_path}.",
            DeprecationWarning,
            stacklevel=2
        )
        _data_dir_cache = legacy_path
        return legacy_path
    
    # Default to new location (will be created when needed)
    _data_dir_cache = new_path
    return new_path


def get_sessions_dir() -> Path:
    """
    Get sessions directory.
    
    Returns:
        Path to ~/.praisonai/sessions/
    """
    return get_data_dir() / "sessions"


def get_skills_dir() -> Path:
    """
    Get user skills directory.
    
    Returns:
        Path to ~/.praisonai/skills/
    """
    return get_data_dir() / "skills"


def get_plugins_dir() -> Path:
    """
    Get user plugins directory.
    
    Returns:
        Path to ~/.praisonai/plugins/
    """
    return get_data_dir() / "plugins"


def get_mcp_dir() -> Path:
    """
    Get MCP config directory.
    
    Returns:
        Path to ~/.praisonai/mcp/
    """
    return get_data_dir() / "mcp"


def get_docs_dir() -> Path:
    """
    Get docs directory.
    
    Returns:
        Path to ~/.praisonai/docs/
    """
    return get_data_dir() / "docs"


def get_rules_dir() -> Path:
    """
    Get rules directory.
    
    Returns:
        Path to ~/.praisonai/rules/
    """
    return get_data_dir() / "rules"


def get_permissions_dir() -> Path:
    """
    Get permissions directory.
    
    Returns:
        Path to ~/.praisonai/permissions/
    """
    return get_data_dir() / "permissions"


def get_storage_dir() -> Path:
    """
    Get generic storage directory.
    
    Returns:
        Path to ~/.praisonai/storage/
    """
    return get_data_dir() / "storage"


def get_checkpoints_dir() -> Path:
    """
    Get checkpoints directory.
    
    Returns:
        Path to ~/.praisonai/checkpoints/
    """
    return get_data_dir() / "checkpoints"


def get_snapshots_dir() -> Path:
    """
    Get snapshots directory.
    
    Returns:
        Path to ~/.praisonai/snapshots/
    """
    return get_data_dir() / "snapshots"


def get_learn_dir() -> Path:
    """
    Get learn directory for learning stores.
    
    Returns:
        Path to ~/.praisonai/learn/
    """
    return get_data_dir() / "learn"


def get_cache_dir() -> Path:
    """
    Get cache directory (disposable data).
    
    Returns:
        Path to ~/.praisonai/cache/
    """
    return get_data_dir() / "cache"


def get_mcp_auth_path() -> Path:
    """
    Get path to MCP auth storage file.
    
    Returns:
        Path to ~/.praisonai/mcp-auth.json
    """
    return get_data_dir() / "mcp-auth.json"


def get_memory_dir() -> Path:
    """
    Get memory directory for short/long term databases.
    
    Returns:
        Path to ~/.praisonai/memory/
    """
    return get_data_dir() / "memory"


def get_workflows_dir() -> Path:
    """
    Get workflows directory.
    
    Returns:
        Path to ~/.praisonai/workflows/
    """
    return get_data_dir() / "workflows"


def get_summaries_dir() -> Path:
    """
    Get summaries directory for RAG.
    
    Returns:
        Path to ~/.praisonai/summaries/
    """
    return get_data_dir() / "summaries"


def get_prp_dir() -> Path:
    """
    Get PRP (Prompt Response Pair) output directory.
    
    Returns:
        Path to ~/.praisonai/prp/
    """
    return get_data_dir() / "prp"


def get_runs_dir() -> Path:
    """
    Get runs directory for artifacts.
    
    Returns:
        Path to ~/.praisonai/runs/
    """
    return get_data_dir() / "runs"


def get_project_data_dir(project_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Get project-level data directory.
    
    Args:
        project_path: Project root (defaults to cwd)
        
    Returns:
        Path to .praisonai/ in project
    
    Example:
        >>> from praisonaiagents.paths import get_project_data_dir
        >>> project_dir = get_project_data_dir("/path/to/project")
        >>> print(project_dir)
        /path/to/project/.praisonai
    """
    if project_path is None:
        base = Path.cwd()
    elif isinstance(project_path, str):
        base = Path(project_path)
    else:
        base = project_path
    return base / DEFAULT_DIR_NAME


def ensure_dir(path: Union[str, Path]) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path to ensure exists
        
    Returns:
        Path object for the directory
    
    Example:
        >>> from praisonaiagents.paths import ensure_dir, get_sessions_dir
        >>> sessions = ensure_dir(get_sessions_dir())
    """
    if isinstance(path, str):
        path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_all_paths() -> Dict[str, Path]:
    """
    Get all PraisonAI data paths.
    
    Returns:
        Dictionary mapping path names to Path objects
    
    Example:
        >>> from praisonaiagents.paths import get_all_paths
        >>> paths = get_all_paths()
        >>> for name, path in paths.items():
        ...     print(f"{name}: {path}")
    """
    return {
        "data_dir": get_data_dir(),
        "sessions": get_sessions_dir(),
        "skills": get_skills_dir(),
        "plugins": get_plugins_dir(),
        "mcp": get_mcp_dir(),
        "docs": get_docs_dir(),
        "rules": get_rules_dir(),
        "permissions": get_permissions_dir(),
        "storage": get_storage_dir(),
        "checkpoints": get_checkpoints_dir(),
        "snapshots": get_snapshots_dir(),
        "learn": get_learn_dir(),
        "cache": get_cache_dir(),
        "mcp_auth": get_mcp_auth_path(),
        "memory": get_memory_dir(),
        "workflows": get_workflows_dir(),
        "summaries": get_summaries_dir(),
        "prp": get_prp_dir(),
        "runs": get_runs_dir(),
    }
