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
