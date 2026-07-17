"""Plugin registry base for praisonai-sandbox (lazy code-bridge import)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praisonai_code._registry import PluginRegistry, create_lazy_getattr

logger = logging.getLogger(__name__)

__all__ = ["PluginRegistry", "create_lazy_getattr", "logger"]


def __getattr__(name: str):
    if name in ("PluginRegistry", "create_lazy_getattr"):
        from praisonai_sandbox._code_bridge import import_code_module

        registry = import_code_module("praisonai_code._registry")
        return getattr(registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
