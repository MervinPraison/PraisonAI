"""Path containment helpers for tool and context safety."""

from __future__ import annotations

import os
from typing import Optional


def resolve_within_root(path: str, root: Optional[str] = None) -> Optional[str]:
    """Resolve *path* under *root* and reject traversal outside the root."""
    base = os.path.realpath(root or os.getcwd())
    expanded = os.path.expanduser(path)
    candidate = (
        os.path.join(base, expanded)
        if not os.path.isabs(expanded)
        else expanded
    )
    resolved = os.path.realpath(os.path.normpath(candidate))
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
    base = os.path.realpath(root or os.getcwd())
    expanded = os.path.expanduser(os.path.expandvars(path))
    candidate = (
        expanded if os.path.isabs(expanded) else os.path.join(base, expanded)
    )
    resolved = os.path.realpath(os.path.normpath(candidate))
    try:
        return os.path.commonpath([resolved, base]) == base
    except ValueError:
        return False
