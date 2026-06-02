"""Expose praisonaiagents HookRegistry for admin/API consumers."""

from __future__ import annotations

from typing import Any, Dict, List


def list_hooks_for_api() -> List[Dict[str, Any]]:
    """Flat hook list suitable for REST responses."""
    try:
        from praisonaiagents.hooks.registry import list_hooks_for_api as core_list

        return core_list()
    except ImportError:
        return []
