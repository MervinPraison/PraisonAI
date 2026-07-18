"""Stable workspace/project identity for default session scoping.

Used by the core ``Agent`` to derive a default (auto) session id that is
workspace-aware, so two same-named agents in different projects do not silently
share conversation history (Issue #3154).

Resolution order for :func:`workspace_id`:

1. Git identity — the repository's root-commit sha (stable across clones,
   independent of local path), when the working directory is inside a git repo.
2. The absolute, resolved current working directory.
3. ``"global"`` as a last resort.

The returned value is an opaque, stable string; callers hash it together with
the agent name to form the session id.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache

__all__ = ["workspace_id"]


def _git_root_commit() -> str | None:
    """Return the repo's first (root) commit sha, or ``None`` if unavailable.

    The root commit is stable across clones and independent of the checkout
    path, making it a good project identity. Falls back silently when git is
    absent or the cwd is not a repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    # A repo may report multiple root commits; the last line is the earliest.
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        return None
    return lines[-1]


@lru_cache(maxsize=None)
def _resolve() -> str:
    root = _git_root_commit()
    if root:
        return f"git:{root}"
    try:
        return f"dir:{os.path.realpath(os.getcwd())}"
    except OSError:
        return "global"


def workspace_id() -> str:
    """Return a stable identity for the current workspace/project.

    Prefers a git root-commit identity, falls back to the resolved cwd, then
    ``"global"``. Cached for the process lifetime.
    """
    return _resolve()
