"""
Configuration paths for PraisonAI CLI.

Defines standard locations for configuration files.
"""

import os
from pathlib import Path
from typing import List, Optional


# Directory markers that identify a PraisonAI project root.
# Order matters: the first existing marker is used as the config directory
# so that detection and config read/write stay aligned.
_PROJECT_MARKERS = (".praison", ".praisonai")
# Default config directory name used when no marker exists yet.
_DEFAULT_CONFIG_DIRNAME = ".praison"
# VCS markers used as a fallback when no project config dir is present.
_VCS_MARKERS = (".git",)


def _config_dirname_for(root: Path) -> str:
    """Return the config directory name to use under ``root``.

    Prefers an existing project marker directory so that a repo created with
    ``.praisonai`` reads and writes config from the same directory it was
    detected by, rather than silently switching to ``.praison``.
    """
    for marker in _PROJECT_MARKERS:
        if (root / marker).is_dir():
            return marker
    return _DEFAULT_CONFIG_DIRNAME


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
        try:
            override_path = Path(override).expanduser().resolve()
        except (OSError, ValueError):
            override_path = None
        # Only honour an override that points to an existing directory;
        # an invalid value falls through to normal discovery rather than
        # aborting or anchoring config writes to a bogus path.
        if override_path is not None and override_path.is_dir():
            return override_path

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


def home_root() -> Path:
    """Return the single canonical PraisonAI home root.

    Delegates to the core ``praisonaiagents.paths.get_data_dir`` so the wrapper
    CLI and the SDK never diverge: honours the ``PRAISONAI_HOME`` override,
    defaults to ``~/.praisonai``, and falls back to a legacy ``~/.praison`` only
    when that is the sole directory present. Falling back to a bare
    ``~/.praisonai`` keeps the CLI working even if the core package is
    unavailable for any reason.
    """
    try:
        from praisonaiagents.paths import get_data_dir

        return get_data_dir()
    except Exception:
        env_path = os.environ.get("PRAISONAI_HOME")
        if env_path:
            return Path(env_path).expanduser()
        return Path.home() / ".praisonai"


def get_user_config_dir() -> Path:
    """Get user configuration directory (canonical home root, e.g. ~/.praisonai/)."""
    return home_root()


def _legacy_user_config_dir() -> Path:
    """Legacy user configuration directory (~/.praison/), read-only fallback."""
    return Path.home() / ".praison"


def get_user_config_path() -> Path:
    """Get user configuration file path (config.toml under the home root).

    Prefers the canonical home root. For backward compatibility, when no config
    exists there but a legacy ``~/.praison/config.toml`` does, the legacy path is
    returned so existing installs keep resolving until migrated.
    """
    primary = get_user_config_write_path()
    if primary.exists():
        return primary
    legacy = _legacy_user_config_dir() / "config.toml"
    if legacy.exists():
        return legacy
    return primary


def _canonical_home_root() -> Path:
    """Canonical home root for *writes*, ignoring the legacy fallback.

    Honours ``PRAISONAI_HOME`` (with ``~`` expansion, matching the core SDK and
    ``setup``) but, unlike :func:`home_root`, never resolves to the legacy
    ``~/.praison`` directory even when it is the only one present — writes must
    always land on the canonical location.
    """
    env_path = os.environ.get("PRAISONAI_HOME")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".praisonai"


def get_user_config_write_path() -> Path:
    """Get the canonical user config file path for *writing*.

    Always resolves to ``config.toml`` under the canonical ``~/.praisonai`` home
    (or ``PRAISONAI_HOME``) and never the legacy ``~/.praison`` location — even
    when only the legacy directory currently exists. Writers (e.g. ``config
    set``/``reset``) must use this so an update never mutates the legacy
    read-only fallback; new values are always persisted to the canonical file.
    """
    return _canonical_home_root() / "config.toml"


def get_project_config_dir(project_root: Optional[Path] = None) -> Path:
    """Get project configuration directory (.praison/).

    When no ``project_root`` is given, the root is discovered by walking up
    from the current working directory via :func:`find_project_root`, so the
    project config is found from any sub-directory. Falls back to cwd when no
    project marker is present.
    """
    root = project_root or find_project_root() or Path.cwd()
    return root / _config_dirname_for(root)


def get_project_config_path(project_root: Optional[Path] = None) -> Path:
    """Get project configuration file path (.praison/config.toml)."""
    return get_project_config_dir(project_root) / "config.toml"


# ---------------------------------------------------------------------------
# Project-local data directory (the one *single* source of truth)
#
# Nine CLI features each hard-coded their own ``".praison/<file>"`` literal
# while the runtime reads ``.praisonai/`` (``praisonaiagents.paths``). That is
# not a cosmetic inconsistency: ``.praison`` is the FIRST entry of
# ``_PROJECT_MARKERS``, so the moment one of those features creates
# ``./.praison/`` in a project whose config lives in ``./.praisonai/``, this
# module's own ``_config_dirname_for`` flips and the project's
# ``.praisonai/config.toml`` silently stops being read.
#
# Everything project-local must therefore go through these helpers rather than
# a literal, so the tenth feature cannot drift again.
# ---------------------------------------------------------------------------

def _canonical_project_dirname() -> str:
    """The canonical project data directory name (``.praisonai``).

    Taken from ``praisonaiagents.paths.DEFAULT_DIR_NAME`` so the wrapper CLI and
    the SDK can never disagree; the literal is only a fallback for a standalone
    ``praisonai-code`` install without the core package.
    """
    try:
        from praisonaiagents.paths import DEFAULT_DIR_NAME

        return DEFAULT_DIR_NAME
    except Exception:  # noqa: BLE001 - never fail on a missing core package
        return ".praisonai"


#: Canonical project data directory name. Import this instead of writing
#: ``".praisonai"`` (or, worse, ``".praison"``) anywhere.
PROJECT_DATA_DIRNAME = _canonical_project_dirname()

#: Legacy project data directory name, kept for *read-only* fallback so an
#: existing ``./.praison/thinking.json`` is still found after the fix.
LEGACY_PROJECT_DATA_DIRNAME = ".praison"


def get_project_data_dir(project_root: Optional[Path] = None) -> Path:
    """Return the canonical project data directory (``<root>/.praisonai``).

    Unlike :func:`get_project_config_dir`, this never resolves to the legacy
    ``.praison`` name: writes must always land where the runtime reads.
    """
    root = project_root if project_root is not None else Path.cwd()
    return Path(root) / PROJECT_DATA_DIRNAME


def get_project_data_path(*parts: str, project_root: Optional[Path] = None) -> Path:
    """Canonical *write* path for a project-local data file.

    ``get_project_data_path("thinking.json")`` -> ``<cwd>/.praisonai/thinking.json``.
    """
    return get_project_data_dir(project_root).joinpath(*parts)


def resolve_project_data_path(
    *parts: str, project_root: Optional[Path] = None
) -> Path:
    """Canonical *read* path, falling back to the legacy ``.praison`` location.

    Returns the canonical path when it exists, otherwise an existing legacy
    ``<root>/.praison/<parts>`` (so data written before this fix is still
    found), otherwise the canonical path again. Reads fall back; writes never
    do -- use :func:`get_project_data_path` to save.
    """
    canonical = get_project_data_path(*parts, project_root=project_root)
    if canonical.exists():
        return canonical
    root = project_root if project_root is not None else Path.cwd()
    legacy = Path(root).joinpath(LEGACY_PROJECT_DATA_DIRNAME, *parts)
    if legacy.exists():
        return legacy
    return canonical


def get_knowledge_store_path(collection: str) -> str:
    """Default on-disk vector-store location for a knowledge collection.

    ``./.praisonai/knowledge/<collection>``, derived from the one canonical
    constant. An existing legacy ``./.praison/knowledge/<collection>`` is still
    used so a collection indexed before this fix is not orphaned.

    Returned as a relative path string because that is what the knowledge
    config consumers expect, and it must stay relative to whatever directory
    the command is run from.
    """
    canonical = f"./{PROJECT_DATA_DIRNAME}/knowledge/{collection}"
    legacy = f"./{LEGACY_PROJECT_DATA_DIRNAME}/knowledge/{collection}"
    if not os.path.exists(canonical) and os.path.exists(legacy):
        return legacy
    return canonical


def get_state_dir() -> Path:
    """Return the machine-local state directory (MRU model, logs, spill).

    Delegates to the core ``praisonaiagents.paths.get_state_dir`` so the wrapper
    and SDK never diverge: honours ``PRAISONAI_HOME`` / an existing single root,
    and otherwise resolves to ``$XDG_STATE_HOME/praisonai`` (else
    ``~/.local/state/praisonai``). Falls back to the canonical home root if the
    core package is unavailable for any reason.
    """
    try:
        from praisonaiagents.paths import get_state_dir as _core_state_dir

        return _core_state_dir()
    except Exception:
        return home_root()


def get_sessions_dir() -> Path:
    """Get sessions directory under the canonical home root (e.g. ~/.praisonai/sessions/)."""
    return get_user_config_dir() / "sessions"


def get_traces_dir() -> Path:
    """Get traces directory under the canonical home root (e.g. ~/.praisonai/traces/)."""
    return get_user_config_dir() / "traces"


def get_logs_dir() -> Path:
    """Get logs directory under the state home (e.g. ~/.praisonai/logs/ or state)."""
    return get_state_dir() / "logs"


def get_cache_dir() -> Path:
    """Get cache directory under the canonical home root (e.g. ~/.praisonai/cache/)."""
    return get_user_config_dir() / "cache"


def get_config_paths(project_root: Optional[Path] = None) -> List[Path]:
    """
    Get all configuration file paths in precedence order (highest first).
    
    Precedence (highest first):
    1. Project configs along the ancestor chain (nearest cwd wins, then
       farther ancestors up to the project root): .praison/config.toml
    2. User config under the canonical home root (config.toml), with a
       read-only fallback to the legacy ~/.praison/config.toml.

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
        project_config = (root / _config_dirname_for(root) / "config.toml")
        if not project_config.exists():
            continue
        resolved = project_config.resolve()
        if resolved not in seen:
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
    # No project marker anywhere above cwd: don't walk to the filesystem
    # root, otherwise an unrelated ancestor's .praison/config.toml would be
    # picked up with higher precedence than the user config.
    if project_root is None:
        return [cur]

    roots: List[Path] = []
    for d in (cur, *cur.parents):
        roots.append(d)
        if d == project_root:
            break
    else:
        # project_root is outside the cwd ancestry (e.g. PRAISONAI_PROJECT
        # override pointing elsewhere): honour it explicitly.
        roots.append(project_root)
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
