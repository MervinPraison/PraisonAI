"""
Configuration paths for PraisonAI CLI.

Defines standard locations for configuration files.
"""

import os
from pathlib import Path
from typing import List, Optional


# Directory markers that identify a PraisonAI project root.
_PROJECT_MARKERS = (".praison", ".praisonai")
# VCS markers used as a fallback when no project config dir is present.
_VCS_MARKERS = (".git",)


def find_project_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from ``start`` (or cwd) to locate the project root.

    The project root is the nearest ancestor (including ``start`` itself)
    that contains a project marker directory (``.praison``/``.praisonai``)
    or a VCS root (``.git``). This lets the CLI behave identically from any
    sub-directory of a project tree.

    An explicit override may be supplied via the ``PRAISONAI_PROJECT``
    environment variable, in which case that path is returned directly.

    Returns:
        The resolved project root, or ``None`` if no marker is found.
    """
    override = os.environ.get("PRAISONAI_PROJECT")
    if override:
        return Path(override).expanduser().resolve()

    try:
        cur = (start or Path.cwd()).resolve()
    except (OSError, ValueError):
        return None

    for d in (cur, *cur.parents):
        if any((d / m).is_dir() for m in _PROJECT_MARKERS):
            return d
        if any((d / m).exists() for m in _VCS_MARKERS):
            return d
    return None


def get_user_config_dir() -> Path:
    """Get user configuration directory (~/.praison/)."""
    return Path.home() / ".praison"


def get_user_config_path() -> Path:
    """Get user configuration file path (~/.praison/config.toml)."""
    return get_user_config_dir() / "config.toml"


def get_project_config_dir(project_root: Optional[Path] = None) -> Path:
    """Get project configuration directory (.praison/).

    When no ``project_root`` is given, the root is discovered by walking up
    from the current working directory via :func:`find_project_root`, so the
    project config is found from any sub-directory. Falls back to cwd when no
    project marker is present.
    """
    root = project_root or find_project_root() or Path.cwd()
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
    
    Precedence (highest first):
    1. Project configs along the ancestor chain (nearest cwd wins, then
       farther ancestors up to the project root): .praison/config.toml
    2. User config: ~/.praison/config.toml

    When no ``project_root`` is supplied, the chain is collected by walking
    up from cwd to the detected project root so the CLI behaves identically
    from any sub-directory.

    Returns:
        List of paths in precedence order
    """
    paths: List[Path] = []
    seen: set = set()

    if project_root is not None:
        roots = [project_root]
    else:
        roots = _project_config_search_roots()

    # Project configs (highest precedence), nearest-to-cwd first.
    for root in roots:
        project_config = (root / ".praison" / "config.toml")
        resolved = project_config.resolve() if project_config.exists() else None
        if resolved and resolved not in seen and project_config.exists():
            seen.add(resolved)
            paths.append(project_config)

    # User config
    user_config = get_user_config_path()
    if user_config.exists() and user_config.resolve() not in seen:
        paths.append(user_config)

    return paths


def _project_config_search_roots() -> List[Path]:
    """Return candidate roots from cwd up to the project root (nearest first)."""
    try:
        cur = Path.cwd().resolve()
    except (OSError, ValueError):
        return []

    project_root = find_project_root(cur)
    roots: List[Path] = []
    for d in (cur, *cur.parents):
        roots.append(d)
        if project_root is not None and d == project_root:
            break
    return roots


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
