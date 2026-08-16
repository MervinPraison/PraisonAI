"""
Centralized Path Utilities for PraisonAI Agents.

All persistent data uses ~/.praisonai/ by default. Override with the
PRAISONAI_HOME environment variable for a single-root layout.

For fresh installs (no PRAISONAI_HOME and no existing ~/.praisonai or
~/.praison), the XDG Base Directory specification is honoured when the
corresponding variables are set:
    config -> $XDG_CONFIG_HOME/praisonai  (else ~/.config/praisonai)
    data   -> $XDG_DATA_HOME/praisonai    (else ~/.praisonai)
    state  -> $XDG_STATE_HOME/praisonai   (else ~/.local/state/praisonai)
    cache  -> $XDG_CACHE_HOME/praisonai   (else ~/.cache/praisonai)
An existing single root (PRAISONAI_HOME or ~/.praisonai/~/.praison) keeps all
classes together, preserving full backward compatibility.

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

# App directory name used under XDG base directories.
XDG_APP_NAME = "praisonai"

# Cache for data dir to avoid repeated filesystem checks
_data_dir_cache: Optional[Path] = None

# Cache for the single-root decision. Snapshotted on first resolution so that
# creating the default data directory later in the same process does not
# retroactively flip config/state/cache from their XDG locations onto a
# single root (see Issue #3981). ``False`` means "resolved: no single root".
_single_root_cache: Union[Path, bool, None] = None


def _clear_cache() -> None:
    """Clear cached path decisions. Used for testing."""
    global _data_dir_cache, _single_root_cache
    _data_dir_cache = None
    _single_root_cache = None


def _single_root() -> Optional[Path]:
    """Return an explicit single-root home if one applies, else ``None``.

    A single root applies when the user has opted into one (``PRAISONAI_HOME``)
    or already has an existing legacy home (``~/.praisonai`` or ``~/.praison``).
    In that case every directory class (config/data/state/cache) stays under
    that single root, preserving full backward compatibility. When no such root
    exists (a fresh install), ``None`` is returned so callers fall through to
    the XDG base directories.

    ``PRAISONAI_HOME`` is always honoured live (never cached) so tests and
    runtime overrides take effect immediately. The existence-based legacy
    detection, however, is snapshotted on first use: once a run has resolved
    "no single root", later creation of the default ``~/.praisonai`` data
    directory must not retroactively move config/state/cache onto it mid-run.
    """
    env_path = os.environ.get(ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()

    global _single_root_cache
    if _single_root_cache is not None:
        return _single_root_cache or None

    home = Path.home()
    new_path = home / DEFAULT_DIR_NAME
    if new_path.exists():
        _single_root_cache = new_path
        return new_path

    legacy_path = home / LEGACY_DIR_NAME
    if legacy_path.exists():
        _single_root_cache = legacy_path
        return legacy_path

    _single_root_cache = False
    return None


def _xdg_dir(base_env: str, default_subpath: str) -> Path:
    """Resolve an XDG base directory for PraisonAI.

    Uses ``$base_env`` when it is set to an absolute path, otherwise the XDG
    default under the home directory, and appends the app name.
    """
    base = os.environ.get(base_env)
    if base and os.path.isabs(base):
        root = Path(base)
    else:
        root = Path.home() / default_subpath
    return root / XDG_APP_NAME


def get_data_dir() -> Path:
    """
    Get PraisonAI data directory.
    
    Priority:
    1. PRAISONAI_HOME env var
    2. ~/.praisonai/ (existing install)
    3. ~/.praison/ (legacy fallback with warning)
    4. $XDG_DATA_HOME/praisonai (only when XDG_DATA_HOME is explicitly set
       and no legacy root exists)
    5. ~/.praisonai/ (default for fresh installs)
    
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
        from .utils.deprecation import warn_deprecated_param
        warn_deprecated_param(
            "legacy data directory",
            since="1.0.0",
            removal="2.0.0",
            alternative=f"run 'praisonai migrate-data' to migrate to {new_path}",
            details=f"Using legacy directory {legacy_path}",
            stacklevel=3
        )
        _data_dir_cache = legacy_path
        return legacy_path
    
    # No single-root install present: honour XDG_DATA_HOME when explicitly set
    # (servers/containers/CI point it at the correct persistent volume).
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data and os.path.isabs(xdg_data):
        xdg_path = Path(xdg_data) / XDG_APP_NAME
        _data_dir_cache = xdg_path
        return xdg_path
    
    # Default to branded location (will be created when needed)
    _data_dir_cache = new_path
    return new_path


def get_config_dir() -> Path:
    """
    Get PraisonAI config directory (editable config, credentials, rules).

    Precedence:
    1. ``PRAISONAI_HOME`` / existing legacy home (single root, back-compat)
    2. ``$XDG_CONFIG_HOME/praisonai`` (else ``~/.config/praisonai``)

    Returns:
        Path to config directory
    """
    root = _single_root()
    if root is not None:
        return root
    return _xdg_dir("XDG_CONFIG_HOME", ".config")


def get_state_dir() -> Path:
    """
    Get PraisonAI state directory (machine-local: MRU model, logs, spill).

    Precedence:
    1. ``PRAISONAI_HOME`` / existing legacy home (single root, back-compat)
    2. ``$XDG_STATE_HOME/praisonai`` (else ``~/.local/state/praisonai``)

    Returns:
        Path to state directory
    """
    root = _single_root()
    if root is not None:
        return root
    return _xdg_dir("XDG_STATE_HOME", ".local/state")


def get_sessions_dir() -> Path:
    """
    Get sessions directory.
    
    Returns:
        Path to ~/.praisonai/sessions/
    """
    return get_data_dir() / "sessions"


def get_session_spill_dir() -> Path:
    """
    Get the session spill directory (last-resort salvage on write failure).

    When a durable session write fails (disk-full / corruption / permission),
    the already-produced turn is spilled here atomically and re-ingested on the
    next load (Issue #3597).

    Returns:
        Path to <state>/state/session_spill/
    """
    return get_state_dir() / "state" / "session_spill"


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

    Under a single-root install this is ``<root>/cache``; on a fresh install it
    resolves to ``$XDG_CACHE_HOME/praisonai`` (else ``~/.cache/praisonai``).

    Returns:
        Path to cache directory
    """
    root = _single_root()
    if root is not None:
        return root / "cache"
    return _xdg_dir("XDG_CACHE_HOME", ".cache")


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


def get_project_sessions_dir(project_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Get project-level sessions directory.
    
    Args:
        project_path: Project root (defaults to cwd)
        
    Returns:
        Path to .praisonai/sessions/ in project
    """
    return get_project_data_dir(project_path) / "sessions"


def get_project_knowledge_dir(project_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Get project-level knowledge directory.
    
    Args:
        project_path: Project root (defaults to cwd)
        
    Returns:
        Path to .praisonai/knowledge/ in project
    """
    return get_project_data_dir(project_path) / "knowledge"


def get_project_summaries_dir(project_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Get project-level summaries directory for RAG.
    
    Args:
        project_path: Project root (defaults to cwd)
        
    Returns:
        Path to .praisonai/summaries/ in project
    """
    return get_project_data_dir(project_path) / "summaries"


def get_project_prp_dir(project_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Get project-level PRP output directory.
    
    Args:
        project_path: Project root (defaults to cwd)
        
    Returns:
        Path to .praisonai/prp/ in project
    """
    return get_project_data_dir(project_path) / "prp"


def get_config_path() -> Path:
    """
    Get path to the main config.yaml file.

    Returns:
        Path to <config>/config.yaml
    """
    return get_config_dir() / "config.yaml"


def get_schedules_dir() -> Path:
    """
    Get schedules directory.
    
    Returns:
        Path to ~/.praisonai/schedules/
    """
    return get_data_dir() / "schedules"


def get_storage_path() -> Path:
    """
    Get default SQLite storage database path.
    
    Returns:
        Path to ~/.praisonai/storage.db
    """
    return get_data_dir() / "storage.db"


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
        "config_dir": get_config_dir(),
        "state_dir": get_state_dir(),
        "sessions": get_sessions_dir(),
        "skills": get_skills_dir(),
        "plugins": get_plugins_dir(),
        "mcp": get_mcp_dir(),
        "docs": get_docs_dir(),
        "rules": get_rules_dir(),
        "permissions": get_permissions_dir(),
        "storage": get_storage_dir(),
        "storage_db": get_storage_path(),
        "schedules": get_schedules_dir(),
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
