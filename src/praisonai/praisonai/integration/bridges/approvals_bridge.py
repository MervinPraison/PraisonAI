"""ApprovalRegistry CRUD adapter for aiui backends."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def list_pending_approvals() -> List[Dict[str, Any]]:
    try:
        from praisonaiagents.approval import get_approval_registry

        registry = get_approval_registry()
        backend = getattr(registry, "_backend", None)
        if backend and hasattr(backend, "list_pending"):
            return backend.list_pending()
    except ImportError:
        pass
    return []


def get_approval_policies() -> Dict[str, Any]:
    try:
        from praisonaiagents.approval import get_approval_registry

        registry = get_approval_registry()
        return {
            "auto_approve_env": registry.is_env_auto_approve(),
            "requirements": getattr(registry, "_requirements", {}),
        }
    except ImportError:
        return {}
