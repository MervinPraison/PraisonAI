"""AGENTS.md-style context file injection for host apps."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

DEFAULT_CANDIDATES = ["AGENTS.md", "agents.md", ".agents/AGENTS.md", "CLAUDE.md"]


def _get_git_root(start: Path) -> Optional[Path]:
    """Resolve the git/project root, reusing the CLI resolver helper.

    Falls back to None when the helper or git is unavailable so discovery
    simply walks up to the filesystem root.
    """
    try:
        from praisonai.cli.utils.project import get_git_root

        return get_git_root(str(start))
    except (ImportError, OSError):
        return None


# When no git root is found, cap the walk-up to avoid scanning arbitrary
# system directories up to the filesystem root.
_MAX_WALK_UP_DEPTH = 10


def _discover_search_dirs(base: Path, walk_up: bool) -> List[Path]:
    """Build directories to search, ordered root -> cwd (nearest last).

    Walks up from ``base`` to the git root so nearer, more specific
    instruction files take precedence by appearing last. When no git root
    is found, the walk-up is capped at ``_MAX_WALK_UP_DEPTH`` levels to avoid
    scanning arbitrary system directories.
    """
    base = base.resolve()
    if not walk_up:
        return [base]

    git_root = _get_git_root(base)
    if git_root is not None:
        git_root = git_root.resolve()

    dirs: List[Path] = []
    current = base
    depth = 0
    while True:
        dirs.append(current)
        if git_root and current == git_root:
            break
        if current == current.parent:
            break
        if git_root is None and depth >= _MAX_WALK_UP_DEPTH:
            break
        current = current.parent
        depth += 1

    # Reverse so root is first and cwd (nearest) is last.
    dirs.reverse()
    return dirs


def load_context_files(
    paths: Optional[List[str]] = None,
    *,
    cwd: Optional[Path] = None,
    walk_up: bool = True,
) -> str:
    """Load context from AGENTS.md-style files and return combined text.

    Discovery mirrors the configuration resolver: it walks up from ``cwd``
    to the project boundary (git root) collecting instruction files at each
    level, layers a user-global file (``~/.praisonai/AGENTS.md``) as the
    lowest-precedence source, and concatenates root -> cwd so nearer files
    take precedence (appear last).

    Args:
        paths: Explicit relative file names to load from ``cwd`` only. When
            provided, discovery/walk-up is skipped (backward compatible).
        cwd: Directory to start discovery from (defaults to ``Path.cwd()``).
        walk_up: When True (default), walk up to the git/project root and
            layer files. Ignored when ``paths`` is given.

    Returns:
        Combined instruction text, blank-line separated.
    """
    base = cwd or Path.cwd()

    seen: set = set()
    chunks: List[str] = []

    def _add(path: Path) -> None:
        if not path.is_file():
            return
        # De-duplicate by filesystem identity so the same physical file is
        # read once even via different paths or on case-insensitive volumes.
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
        except OSError:
            key = path.resolve()
        if key in seen:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        seen.add(key)
        chunks.append(text)

    # Explicit paths override discovery and remain cwd-only for compatibility.
    if paths is not None:
        for name in paths:
            _add(base / name)
        return "\n\n".join(chunks)

    # Lowest-precedence layer: user-global instructions
    # (skipped when walk_up is False to honour cwd-only semantics).
    if walk_up:
        _add(Path.home() / ".praisonai" / "AGENTS.md")

    # Walk-up layers: root -> cwd so nearer files take precedence (last).
    for search_dir in _discover_search_dirs(base, walk_up):
        for name in DEFAULT_CANDIDATES:
            _add(search_dir / name)

    return "\n\n".join(chunks)
