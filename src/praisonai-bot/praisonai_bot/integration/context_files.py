"""AGENTS.md-style context file injection for host apps."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

DEFAULT_CANDIDATES = ["AGENTS.md", "agents.md", ".agents/AGENTS.md", "CLAUDE.md"]


def _get_git_root(start: Path) -> Optional[Path]:
    """Resolve the git/project root, reusing the CLI resolver helper.

    Falls back to None when the helper or git is unavailable so discovery
    simply walks up to the filesystem root.
    """
    try:
        from praisonai_bot._code_bridge import import_code_module

        project = import_code_module("praisonai_code.cli.utils.project")
        return project.get_git_root(str(start))
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


def _identity_key(path: Path):
    """Filesystem identity for dedup (device+inode), falling back to resolved path."""
    try:
        stat = path.stat()
        return (stat.st_dev, stat.st_ino)
    except OSError:
        return path.resolve()


class PathContextAttacher:
    """Attach the nearest governing instruction files as files are touched.

    Up-front ``load_context_files`` discovery walks ``cwd -> project root`` once
    at session start. In a monorepo, an agent that later reads/edits a file in a
    *sibling or deeper* subtree (e.g. ``packages/foo/AGENTS.md``) never sees that
    subtree's conventions. This attacher augments the up-front load: on the first
    touch of a directory it walks up to the project root collecting
    ``DEFAULT_CANDIDATES``, deduplicates against files already loaded (both the
    up-front rules and earlier touches), bounds the result by a character budget,
    and caches per directory so repeated touches never re-walk disk.

    Session-scoped: create one instance per session/agent run so cache and dedup
    state stay isolated (multi-agent safe).
    """

    def __init__(
        self,
        already_loaded: Optional[str] = None,
        *,
        max_chars: int = 8000,
    ) -> None:
        """Initialise the attacher.

        Args:
            already_loaded: Text already injected up front (used only to seed
                dedup so its files are not re-attached). Its identity is tracked
                by content so duplicate physical files are skipped.
            max_chars: Character budget for the total text this attacher emits
                across the session. ``0`` disables the budget.
        """
        self._seen: Set = set()
        self._dir_cache: Dict[Path, str] = {}
        self._max_chars = max_chars
        self._emitted_chars = 0
        # Seed dedup with the identities of already-loaded files so the same
        # physical instruction file discovered up front is not re-attached.
        if already_loaded:
            self._seed_from_text(already_loaded)

    def _seed_from_text(self, text: str) -> None:
        # We cannot recover file identities from text alone, so we record the
        # text content to skip re-emitting identical bodies. Physical-identity
        # dedup below still handles the same file reached via different paths.
        self._seen_texts: Set[str] = getattr(self, "_seen_texts", set())
        self._seen_texts.add(text)

    def attach_for_path(self, file_path) -> str:
        """Return nearest instruction text for ``file_path``'s directory.

        Walks up from the file's directory to the project root collecting
        instruction files (root first, nearest last), deduplicated against
        everything already emitted/loaded and bounded by the char budget. The
        first touch of a directory does the disk walk; later touches of the same
        directory return the cached (already-deduped) result cheaply.

        Returns an empty string when nothing new is found or the budget is
        exhausted.
        """
        p = Path(file_path)
        directory = (p if p.is_dir() else p.parent).resolve()

        if directory in self._dir_cache:
            return self._dir_cache[directory]

        seen_texts: Set[str] = getattr(self, "_seen_texts", set())
        chunks: List[str] = []
        for search_dir in _discover_search_dirs(directory, walk_up=True):
            for name in DEFAULT_CANDIDATES:
                candidate = search_dir / name
                if not candidate.is_file():
                    continue
                key = _identity_key(candidate)
                if key in self._seen:
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
                if text in seen_texts:
                    self._seen.add(key)
                    continue
                self._seen.add(key)
                seen_texts.add(text)
                chunks.append(text)

        result = "\n\n".join(chunks)

        # Enforce the character budget across the whole session.
        if self._max_chars and result:
            remaining = self._max_chars - self._emitted_chars
            if remaining <= 0:
                result = ""
            elif len(result) > remaining:
                result = result[:remaining] + "\n... [subtree context truncated]"

        self._emitted_chars += len(result)
        self._seen_texts = seen_texts
        self._dir_cache[directory] = result
        return result


def load_context_files_for_path(
    file_path,
    *,
    already_loaded: Optional[str] = None,
    max_chars: int = 8000,
) -> str:
    """Stateless one-shot discovery of nearest instruction files for a path.

    Convenience wrapper around :class:`PathContextAttacher` for callers that do
    not maintain session state. Prefer the class when touching many files so
    dedup and per-directory caching persist across touches.
    """
    return PathContextAttacher(
        already_loaded, max_chars=max_chars
    ).attach_for_path(file_path)
