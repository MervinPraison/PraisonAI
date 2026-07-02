"""Path containment helpers for tool and context safety."""

from __future__ import annotations

import os
from typing import Optional


def resolve_path(path: str, root: Optional[str] = None) -> str:
    """Fully resolve *path* against *root* (real, absolute, ``..``-collapsed).

    Expands ``~`` and environment variables, joins relative paths onto the
    real path of *root* (defaulting to the current working directory) and
    resolves symlinks/``..``. This is the single shared resolver used by all
    workspace-containment checks so boundary logic can never silently diverge.
    """
    base = os.path.realpath(root or os.getcwd())
    expanded = os.path.expanduser(os.path.expandvars(path))
    candidate = (
        expanded if os.path.isabs(expanded) else os.path.join(base, expanded)
    )
    return os.path.realpath(os.path.normpath(candidate))


def resolve_within_root(path: str, root: Optional[str] = None) -> Optional[str]:
    """Resolve *path* under *root*, returning ``None`` if it escapes the root."""
    base = os.path.realpath(root or os.getcwd())
    resolved = resolve_path(path, base)
    try:
        if os.path.commonpath([resolved, base]) != base:
            return None
    except ValueError:
        return None
    return resolved


def is_within_root(path: str, root: Optional[str] = None) -> bool:
    """Return ``True`` if *path* resolves to a location inside *root*.

    Expands ``~`` and environment variables, resolves symlinks/``..`` and
    compares against the real path of *root* (defaulting to the current
    working directory). Paths equal to the root itself are considered within.
    """
    return resolve_within_root(path, root) is not None
