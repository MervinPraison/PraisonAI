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
        m = re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://(?:[^@/]+@)?([^/:]*)(?::\d+)?/(.+)$', url)
        if m:
            host, path = m.group(1), m.group(2)
        else:
            return None

    host = host.lower().strip('/')
    path = path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    if not path:
        return None
    # Host-less remotes (e.g. ``file:///srv/repos/project.git`` or a bare local
    # path) still yield a stable identity from their path alone; only require a
    # host for network remotes that actually have one.
    return f"{host}/{path}" if host else path


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
    # Enumerate root commits across *all* refs (not just those reachable from
    # HEAD) so switching between unmerged orphan branches doesn't change the
    # selected root commit and silently orphan session history.
    #
    # The choice among them must be stable as the repo GAINS roots, which
    # picking the lexicographically smallest SHA is not: creating an orphan
    # branch adds a root, and roughly half the time that new SHA sorts below
    # the existing one -- reassigning the project id and orphaning exactly the
    # history this is meant to protect. Measured at 10/20 on fresh repos.
    #
    # The oldest root is stable instead: a root created later cannot become the
    # oldest. Ties (same commit second, common in scripted setups) fall back to
    # the smallest SHA so the result stays deterministic.
    out = _git_output(
        ['log', '--max-parents=0', '--all', '--format=%ct %H'], cwd)
    if not out:
        # No refs yet (e.g. detached/unborn); fall back to HEAD's roots if any.
        out = _git_output(
            ['log', '--max-parents=0', 'HEAD', '--format=%ct %H'], cwd)
    if not out:
        return None
    roots = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        stamp, sha = parts
        try:
            roots.append((int(stamp), sha))
        except ValueError:
            # Unparseable timestamp: keep the commit, but sort it last so it
            # only wins when nothing else is available.
            roots.append((1 << 62, sha))
    if not roots:
        return None
    available = {sha for _, sha in roots}
    chosen = min(roots)[1]

    # Pin the choice on first resolve. Preferring the oldest root already stops
    # a *later* orphan branch from winning, but two roots created in the same
    # second tie and fall back to the SHA -- which flips about half the time.
    # A pinned SHA cannot drift at all. Re-choose only if the pinned commit is
    # no longer a root here (history rewritten, or a shallow/partial clone).
    pinned_path = _git_meta_path(path, "praisonai-root-commit")
    if pinned_path is not None:
        try:
            if pinned_path.exists():
                pinned = pinned_path.read_text(encoding="utf-8").strip()
                if pinned in available:
                    return pinned
                # A pin naming a commit that is no longer a root here (rewritten
                # history, shallow/partial clone) can't be trusted. Re-pin the
                # freshly chosen root so subsequent resolves stay stable rather
                # than recomputing -- and flipping on same-second ties -- every
                # time. Atomic replace keeps concurrent healers agreeing.
                _atomic_write(pinned_path, chosen)
            else:
                # Exclusive create, like the cached id below: concurrent first
                # runs must agree rather than each pinning its own choice.
                try:
                    with open(pinned_path, "x", encoding="utf-8") as fh:
                        fh.write(chosen)
                except FileExistsError:
                    other = pinned_path.read_text(encoding="utf-8").strip()
                    if other in available:
                        return other
                    # Racing writer pinned a now-stale commit; refresh as above.
                    _atomic_write(pinned_path, chosen)
                except OSError:
                    pass
        except OSError:
            pass
    return chosen


def _atomic_write(target: Path, content: str) -> None:
    """Best-effort atomic overwrite of ``target`` with ``content``.

    Writes to a unique temp file in the same directory and ``os.replace``s it
    into place so a concurrent reader never sees a half-written pin and racing
    healers converge on one file rather than corrupting each other. Failures are
    swallowed: the caller already has the value it will return.
    """
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _git_meta_path(path: Optional[str], name: str) -> Optional[Path]:
    """Return ``<git-common-dir>/<name>`` for the repo containing ``path``.

    ``--git-common-dir`` so every worktree of a repo shares one file.
    """
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
    return git_dir_path / name


def _cached_id_path(path: Optional[str] = None) -> Optional[Path]:
    """Return the path to the persisted project-id file inside ``.git``."""
    return _git_meta_path(path, "praisonai-project")


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
    # Create exclusively so concurrent first-runs don't diverge: only one writer
    # wins, and any loser re-reads the persisted id rather than returning its own
    # (unpersisted) value that no later invocation could resolve.
    try:
        with open(cached_path, "x", encoding="utf-8") as fh:
            fh.write(new_id)
        return new_id
    except FileExistsError:
        try:
            existing = cached_path.read_text(encoding="utf-8").strip()
            return existing or None
        except OSError:
            return None
    except OSError:
        return None


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