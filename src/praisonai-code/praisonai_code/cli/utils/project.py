"""
Project identity utilities for CLI session scoping.

Provides functions to identify the current project context for scoped sessions.
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def get_git_root(path: Optional[str] = None) -> Optional[Path]:
    """
    Find the git repository root from the given path.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Path to git root, or None if not in a git repo
    """
    start_path = Path(path) if path else Path.cwd()
    
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=start_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _git_output(args, cwd) -> Optional[str]:
    """Run a git command and return stripped stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    out = result.stdout.strip()
    return out or None


def normalize_git_remote(url: str) -> Optional[str]:
    """
    Normalise a git remote URL to a stable, path-independent identity string.

    Strips protocol, credentials, and a trailing ``.git`` so equivalent remotes
    (``https``/``ssh``/``git@``) collapse to the same ``host/path`` form.

    Args:
        url: Raw remote URL (e.g. from ``git remote get-url origin``)

    Returns:
        Normalised ``host/path`` string, or None if it can't be parsed.
    """
    if not url:
        return None
    url = url.strip()

    # scp-like syntax: git@host:owner/repo(.git)
    scp = re.match(r'^[^@/]+@([^:/]+):(.+)$', url)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        # protocol://[user[:pass]@]host[:port]/path
        m = re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$', url)
        if m:
            host, path = m.group(1), m.group(2)
        else:
            return None

    host = host.lower().strip('/')
    path = path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    if not host or not path:
        return None
    return f"{host}/{path}"


def get_git_remote_identity(path: Optional[str] = None) -> Optional[str]:
    """Return the normalised remote identity for the repo at ``path``, if any."""
    git_root = get_git_root(path)
    cwd = git_root if git_root else (Path(path) if path else Path.cwd())
    url = _git_output(['remote', 'get-url', 'origin'], cwd)
    if not url:
        # Fall back to the first configured remote of any name.
        remotes = _git_output(['remote'], cwd)
        if remotes:
            first = remotes.splitlines()[0].strip()
            if first:
                url = _git_output(['remote', 'get-url', first], cwd)
    if not url:
        return None
    return normalize_git_remote(url)


def get_git_root_commit(path: Optional[str] = None) -> Optional[str]:
    """Return the repository's root (first) commit SHA, if the repo has commits."""
    git_root = get_git_root(path)
    cwd = git_root if git_root else (Path(path) if path else Path.cwd())
    out = _git_output(['rev-list', '--max-parents=0', 'HEAD'], cwd)
    if not out:
        return None
    # A repo may have multiple root commits; the last line is the earliest.
    return out.splitlines()[-1].strip() or None


def _cached_id_path(path: Optional[str] = None) -> Optional[Path]:
    """Return the path to the persisted project-id file inside ``.git``."""
    git_root = get_git_root(path)
    if not git_root:
        return None
    git_dir = _git_output(['rev-parse', '--git-common-dir'], git_root)
    if not git_dir:
        git_dir = _git_output(['rev-parse', '--git-dir'], git_root)
    if not git_dir:
        return None
    git_dir_path = Path(git_dir)
    if not git_dir_path.is_absolute():
        git_dir_path = (git_root / git_dir_path).resolve()
    return git_dir_path / "praisonai-project"


def get_or_create_cached_id(path: Optional[str] = None) -> Optional[str]:
    """
    Read (or create and persist) a stable project id inside the repo's ``.git``.

    Used for git repos that have neither a remote nor any commits, so their
    identity still survives directory moves/renames. Uses ``--git-common-dir``
    so all worktrees of the same repo share one cached id.
    """
    cached_path = _cached_id_path(path)
    if cached_path is None:
        return None
    try:
        if cached_path.exists():
            existing = cached_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except OSError:
        return None
    new_id = hashlib.sha256(os.urandom(32)).hexdigest()
    try:
        cached_path.write_text(new_id, encoding="utf-8")
    except OSError:
        return None
    return new_id


def _short_hash(value: str) -> str:
    """Collapse an identity string to the existing 8-char short hash."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def resolve_project_identity(path: Optional[str] = None) -> Tuple[str, str]:
    """
    Resolve a stable, path-independent project identity for session scoping.

    Precedence (first hit wins):
      1. Normalised git remote URL  -> source ``git-remote``
      2. Repository root commit SHA -> source ``root-commit``
      3. Cached id in ``.git``      -> source ``cached-id``
      4. Resolved path hash         -> source ``path`` (legacy behaviour)

    All sources collapse to the same 8-char short hash so downstream storage is
    unchanged.

    Args:
        path: Starting path (defaults to cwd)

    Returns:
        ``(project_id, source)`` where ``source`` names the winning strategy.
    """
    remote = get_git_remote_identity(path)
    if remote:
        return _short_hash(f"git-remote:{remote}"), "git-remote"

    root_commit = get_git_root_commit(path)
    if root_commit:
        return _short_hash(f"root-commit:{root_commit}"), "root-commit"

    cached = get_or_create_cached_id(path)
    if cached:
        return _short_hash(f"cached-id:{cached}"), "cached-id"

    git_root = get_git_root(path)
    if git_root:
        project_path = str(git_root.resolve())
    else:
        project_path = str(Path(path).resolve() if path else Path.cwd().resolve())
    return _short_hash(project_path), "path"


def get_legacy_project_id(path: Optional[str] = None) -> str:
    """
    Compute the legacy resolved-path project hash (pre-git-identity behaviour).

    Retained so pre-existing path-scoped session directories remain discoverable
    after the identity resolver is introduced.
    """
    git_root = get_git_root(path)
    if git_root:
        project_path = str(git_root.resolve())
    else:
        project_path = str(Path(path).resolve() if path else Path.cwd().resolve())
    return _short_hash(project_path)


def get_project_id(path: Optional[str] = None) -> str:
    """
    Generate a stable project identifier.

    Resolves a repository-following identity (git remote → root commit → cached
    id) and falls back to the legacy resolved-path hash for non-git directories.
    Returns a short hash (8 chars) for scoped session storage.

    Args:
        path: Starting path (defaults to cwd)

    Returns:
        Short project hash (8 chars)
    """
    project_id, _source = resolve_project_identity(path)
    return project_id


def get_project_identity_source(path: Optional[str] = None) -> str:
    """Return the name of the identity strategy used for ``path`` (transparency)."""
    _project_id, source = resolve_project_identity(path)
    return source


def get_project_name(path: Optional[str] = None) -> str:
    """
    Get a human-readable project name.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Project directory name
    """
    git_root = get_git_root(path)
    if git_root:
        return git_root.name
    
    current_path = Path(path) if path else Path.cwd()
    return current_path.name


def get_project_sessions_dir(path: Optional[str] = None) -> Path:
    """
    Get project-scoped session directory.
    
    Args:
        path: Starting path (defaults to cwd)
        
    Returns:
        Path to project sessions directory
    """
    from praisonaiagents.paths import get_sessions_dir
    
    project_id = get_project_id(path)
    return get_sessions_dir() / f"projects/{project_id}"


def build_cli_memory_config(
    session_id: Optional[str] = None,
    auto_save: Optional[str] = None,
):
    """Build MemoryConfig for CLI session continuity."""
    if not session_id and not auto_save:
        return None
    from praisonaiagents import MemoryConfig

    name = session_id or auto_save
    return MemoryConfig(
        auto_save=auto_save or name,
        history=True,
        session_id=name,
    )


def apply_cli_session_continuity(agent, session_id: Optional[str]) -> None:
    """Wire an agent to the project session store for CLI continuity."""
    if not session_id:
        return

    from ..state.project_sessions import get_project_session_store

    store = get_project_session_store()
    agent._session_id = session_id
    agent._session_store = store
    agent._session_store_initialized = True
    agent._history_enabled = True
    agent._history_session_id = session_id
    
    # Don't pre-populate chat_history - the mixin will load it from _session_store
    # when _history_enabled=True, avoiding duplicate history injection