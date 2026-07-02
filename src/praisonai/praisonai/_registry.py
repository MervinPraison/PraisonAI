"""Backward-compatibility shim for :mod:`praisonai._registry`.

The canonical ``PluginRegistry`` base lives in
:mod:`praisonai_code._registry`. This module re-exports it so the historical
import path (``from praisonai._registry import PluginRegistry``) keeps working
while there is a single owner of the registry-resolution logic (mirroring the
existing ``tool_resolver`` / ``tool_registry`` shims).
"""

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

from praisonai_code._registry import (  # noqa: F401
    PluginRegistry,
    create_lazy_getattr,
)

import logging as _logging

# Preserve the historical logger name so any existing log-level configuration
# targeting ``'praisonai._registry'`` still takes effect (the canonical module's
# logger is named ``'praisonai_code._registry'``).
logger = _logging.getLogger(__name__)

__all__ = ["PluginRegistry", "create_lazy_getattr", "logger"]
