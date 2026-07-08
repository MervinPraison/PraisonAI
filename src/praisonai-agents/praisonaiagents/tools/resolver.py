"""Canonical tool name resolution for the core SDK.

Resolution order (first match wins):
1. Tool registry (explicitly registered tools)
2. praisonaiagents.tools.TOOL_MAPPINGS (built-in lazy tools)
3. praisonai-tools package (external integrations, optional)
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_praisonai_tools_available: Optional[bool] = None


def resolve_tool_name(name: str) -> Optional[Any]:
    """Resolve a single tool name to a callable or tool instance."""
    # 1. Registry
    try:
        from .registry import get_registry

        tool = get_registry().get(name)
        if tool is not None:
            return tool
    except ImportError:
        pass

    # 2. Built-in TOOL_MAPPINGS
    try:
        from . import TOOL_MAPPINGS

        if name in TOOL_MAPPINGS:
            import praisonaiagents.tools as agent_tools

            return getattr(agent_tools, name)
    except AttributeError as exc:
        logger.warning("Tool %r exists in TOOL_MAPPINGS but failed to load: %s", name, exc)
        return None
    except ImportError:
        pass

    # 3. praisonai-tools (optional)
    global _praisonai_tools_available
    if _praisonai_tools_available is None:
        _praisonai_tools_available = importlib.util.find_spec("praisonai_tools") is not None

    if _praisonai_tools_available:
        try:
            import praisonai_tools

            tool = getattr(praisonai_tools, name, None)
            if tool is not None:
                return tool
        except ImportError:
            _praisonai_tools_available = False

    return None


def resolve_tool_names(names: List[str]) -> List[Any]:
    """Resolve tool name strings to callables/instances."""
    resolved = []
    for name in names:
        tool = resolve_tool_name(name)
        if tool is not None:
            resolved.append(tool)
        else:
            logger.warning("Tool %r not found (registry, TOOL_MAPPINGS, praisonai-tools)", name)
    return resolved
