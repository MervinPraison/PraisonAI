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
    # realpath alone: normpath first would fold "link/.." lexically and
    # check a different file than the one the OS opens.
    return os.path.realpath(candidate)


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


def resolve_inside(root: Optional[str], path: str) -> str:
    """Resolve *path* under *root*, raising ``ValueError`` if it escapes.

    The raising form of :func:`resolve_within_root` for file tools: rejects
    absolute paths outside *root*, ``..``, ``~`` outside *root*, sibling
    directories that share *root*'s prefix and symlinks that leave *root*.
    """
    resolved = resolve_within_root(os.fspath(path), os.fspath(root) if root else None)
    if resolved is None:
        raise ValueError(f"Path is outside the workspace: {path}")
    return resolved


def is_within_root(path: str, root: Optional[str] = None) -> bool:
    """Return ``True`` if *path* resolves to a location inside *root*.

    Expands ``~`` and environment variables, resolves symlinks/``..`` and
    compares against the real path of *root* (defaulting to the current
    working directory). Paths equal to the root itself are considered within.
    """
    return resolve_within_root(path, root) is not None
