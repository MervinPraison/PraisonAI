"""
Repository root discovery shared by the parity extractors and generator.

The parity package lives at ``<repo>/src/praisonai/praisonai/_dev/parity``, so
the repository root can be located by walking up from this file until a
directory containing both ``src/praisonai-agents`` and ``src/praisonai-ts`` is
found. The current working directory is tried as a secondary starting point so
that an installed copy of the package still works when run from inside a
checkout. No machine-specific fallback exists: if neither walk succeeds a
``RuntimeError`` is raised asking the caller to pass ``--repo-root``.
"""

from pathlib import Path
from typing import Iterable, Optional

# Directories that must both exist under a candidate root for it to count.
_ROOT_MARKERS = ("src/praisonai-agents", "src/praisonai-ts")


def _is_repo_root(candidate: Path) -> bool:
    return all((candidate / marker).is_dir() for marker in _ROOT_MARKERS)


def _walk_up(start: Path) -> Iterable[Path]:
    current = start.resolve()
    yield current
    while current != current.parent:
        current = current.parent
        yield current


def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Locate the monorepo root.

    Args:
        start: Optional directory to begin walking up from. Defaults to the
            directory containing this module; the current working directory is
            tried afterwards.

    Returns:
        The first ancestor containing both ``src/praisonai-agents`` and
        ``src/praisonai-ts``.

    Raises:
        RuntimeError: If no such directory exists on either walk.
    """
    starts = []
    if start is not None:
        starts.append(Path(start))
    starts.append(Path(__file__).parent)
    starts.append(Path.cwd())

    for origin in starts:
        for candidate in _walk_up(origin):
            if _is_repo_root(candidate):
                return candidate

    tried = ", ".join(str(Path(s).resolve()) for s in starts)
    raise RuntimeError(
        "Could not locate the PraisonAI repository root (a directory containing "
        "both src/praisonai-agents and src/praisonai-ts). Walked up from: "
        f"{tried}. Pass the root explicitly with --repo-root <path>."
    )
