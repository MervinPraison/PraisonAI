"""On-demand attachment of nearby project-instruction files.

Project-instruction files (``AGENTS.md``, ``CLAUDE.md``, ``.agents/AGENTS.md``)
are normally loaded once, up front, by walking from the current working
directory up to the project/git root. In a monorepo, an agent that later reads
or edits a file in a sibling or deeper subtree with its own conventions never
sees that subtree's instruction file.

This module provides a lightweight, path-driven helper: given a file the agent
just read or edited, it discovers the *nearest governing* instruction file(s)
for that file's directory (walking up to the project root), deduplicated
against what is already loaded and bounded by a character budget. Discovery is
cached per directory per session so repeated touches never re-walk the disk.

Design constraints (see AGENTS.md):
- Pure-Python, no new dependencies, no heavy imports.
- Opt-in / backward compatible: nothing runs unless an attacher is created.
- Multi-agent safe: state is instance-scoped, not global.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

# Candidate instruction file names, mirroring the up-front discovery list in
# ``praisonai_bot.integration.context_files.DEFAULT_CANDIDATES`` so up-front and
# on-demand loading share one convention. Ordered general -> specific.
DEFAULT_CANDIDATES: List[str] = [
    "AGENTS.md",
    "agents.md",
    ".agents/AGENTS.md",
    "CLAUDE.md",
]

# Cap the walk-up when no project root is found so we never scan arbitrary
# system directories up to the filesystem root.
_MAX_WALK_UP_DEPTH = 25

# Default budget for on-demand instruction text (characters). Kept modest so a
# deep monorepo touch cannot balloon the prompt.
DEFAULT_MAX_CHARS = 8000


def _find_project_root(start: Path) -> Optional[Path]:
    """Return the nearest ancestor containing a ``.git`` marker, else None."""
    current = start
    while True:
        if (current / ".git").exists():
            return current
        if current == current.parent:
            return None
        current = current.parent


def _is_within(path: Path, root: Path) -> bool:
    """True if ``path`` is ``root`` or a descendant of it."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass
class InstructionFileAttacher:
    """Discover and attach nearest-governing instruction files on demand.

    Create one per session. Call :meth:`attach_for_path` each time the agent
    reads or edits a file; it returns any newly discovered instruction text
    (nearest-wins, budget-bounded) that has not been attached before, or an
    empty string when there is nothing new.

    Args:
        project_root: Boundary for the walk-up. When None, it is resolved per
            path from the nearest ``.git`` ancestor (falling back to a bounded
            walk when no git root exists).
        candidates: Instruction file names to look for (defaults to
            :data:`DEFAULT_CANDIDATES`).
        max_chars: Total character budget across all on-demand attachments in
            this session.
        already_loaded: Text already loaded up front (e.g. via
            ``load_context_files``). Instruction files whose content is already
            present here are skipped, so up-front and on-demand loading never
            duplicate.
    """

    project_root: Optional[Path] = None
    candidates: List[str] = field(default_factory=lambda: list(DEFAULT_CANDIDATES))
    max_chars: int = DEFAULT_MAX_CHARS
    already_loaded: str = ""

    _visited_dirs: Set[Path] = field(default_factory=set, init=False, repr=False)
    _seen_file_keys: Set[tuple] = field(default_factory=set, init=False, repr=False)
    _used_chars: int = field(default=0, init=False, repr=False)
    _preloaded_norms: Set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.project_root is not None:
            self.project_root = Path(self.project_root).resolve()
        # Pre-seed dedup with normalized snapshots of already-loaded blocks so we
        # never re-attach content the up-front loader already supplied. We match
        # whole normalized blocks (exact), not substrings, so a subtree file is
        # never dropped merely because its text appears inside a larger blob.
        self._preloaded_norms = {
            _normalize(block)
            for block in _split_blocks(self.already_loaded)
            if _normalize(block)
        }

    def _search_dirs(self, directory: Path) -> List[Path]:
        """Directories to search for ``directory``, ordered root -> nearest.

        Walks up from ``directory`` to the project root so nearer, more
        specific files take precedence (they appear last).
        """
        directory = directory.resolve()
        root = self.project_root or _find_project_root(directory)
        if root is not None:
            root = root.resolve()

        dirs: List[Path] = []
        current = directory
        depth = 0
        while True:
            dirs.append(current)
            if root is not None and current == root:
                break
            if current == current.parent:
                break
            # Always bound the walk. When ``root`` is set but ``directory`` is
            # outside it, ``current == root`` is never reached; the depth cap
            # then stops us from escaping to arbitrary system directories.
            if depth >= _MAX_WALK_UP_DEPTH:
                break
            current = current.parent
            depth += 1

        # Hard boundary: when an explicit project_root is configured, never
        # surface instruction files from outside it (e.g. the file lives in a
        # sibling tree or a temp dir). Directories not contained in root are
        # dropped, so we cannot read AGENTS.md from home/system directories.
        if self.project_root is not None:
            dirs = [d for d in dirs if _is_within(d, self.project_root)]

        dirs.reverse()
        return dirs

    def _read_instruction(self, path: Path) -> Optional[str]:
        """Read an instruction file once, deduplicated by filesystem identity."""
        if not path.is_file():
            return None
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
        except OSError:
            key = (0, str(path))
        if key in self._seen_file_keys:
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        self._seen_file_keys.add(key)
        if not text.strip():
            return None
        # Skip content already present in the up-front layer. Exact whole-block
        # match (not substring) so a distinct file is never wrongly dropped.
        if _normalize(text) in self._preloaded_norms:
            return None
        return text

    def attach_for_path(self, file_path: str) -> str:
        """Return newly discovered instruction text for ``file_path``.

        Discovers the nearest governing instruction file(s) for the file's
        directory, once per directory per session. Returns combined text
        (blank-line separated, nearest last) bounded by the remaining character
        budget, or an empty string when nothing new is found.
        """
        if self._used_chars >= self.max_chars:
            return ""

        try:
            resolved = Path(file_path).resolve()
        except OSError:
            return ""

        directory = resolved if resolved.is_dir() else resolved.parent
        if directory in self._visited_dirs:
            return ""

        search_dirs = self._search_dirs(directory)
        # Mark every directory on the walk as visited so touching a deeper file
        # in the same subtree does not re-walk.
        for d in search_dirs:
            self._visited_dirs.add(d)

        chunks: List[str] = []
        for search_dir in search_dirs:
            for name in self.candidates:
                text = self._read_instruction(search_dir / name)
                if text is None:
                    continue
                remaining = self.max_chars - self._used_chars
                if remaining <= 0:
                    break
                if len(text) > remaining:
                    # Reserve room for the notice so the emitted chunk never
                    # exceeds the remaining budget.
                    suffix = "\n\n... (truncated)"
                    body = text[: max(remaining - len(suffix), 0)].rstrip()
                    text = body + suffix
                    self._used_chars += remaining
                else:
                    self._used_chars += len(text)
                chunks.append(text)
            if self._used_chars >= self.max_chars:
                break

        return "\n\n".join(chunks)


def _normalize(text: str) -> str:
    """Collapse whitespace for robust whole-block de-duplication."""
    if not text:
        return ""
    return " ".join(text.split())


def _split_blocks(text: str) -> List[str]:
    """Split concatenated already-loaded text into candidate blocks.

    Up-front loaders typically join instruction files with blank lines, so we
    split on that separator to recover individual blocks for exact-match dedup.
    The whole text is also treated as one block to cover single-file inputs.
    """
    if not text:
        return []
    blocks = [b for b in text.split("\n\n") if b.strip()]
    blocks.append(text)
    return blocks


def discover_instruction_files(
    file_path: str,
    *,
    project_root: Optional[str] = None,
    candidates: Optional[List[str]] = None,
) -> List[str]:
    """Return paths of instruction files governing ``file_path``, root -> nearest.

    Stateless convenience helper (no dedup/budget). Useful for wrappers that
    want to discover files without managing an attacher.
    """
    attacher = InstructionFileAttacher(
        project_root=Path(project_root) if project_root else None,
        candidates=list(candidates) if candidates else list(DEFAULT_CANDIDATES),
    )
    try:
        resolved = Path(file_path).resolve()
    except OSError:
        return []
    directory = resolved if resolved.is_dir() else resolved.parent
    found: List[str] = []
    for search_dir in attacher._search_dirs(directory):
        for name in attacher.candidates:
            candidate = search_dir / name
            if candidate.is_file():
                found.append(str(candidate))
    return found
