"""Canonical tool name resolution for the core SDK.

Resolution order (first match wins):
1. Tool registry (explicitly registered tools)
2. praisonaiagents.tools.TOOL_MAPPINGS (built-in lazy tools)
3. praisonai-tools package (external integrations, optional)
"""

from __future__ import annotations

import difflib
import importlib.util
import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_praisonai_tools_available: Optional[bool] = None


class ToolResolutionError(ValueError):
    """Raised in strict mode when one or more tool names cannot be resolved."""

    def __init__(self, unknown: List[str], suggestions: Dict[str, List[str]]):
        self.unknown = unknown
        self.suggestions = suggestions
        super().__init__(_format_unknown(unknown, suggestions))


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
        except Exception:
            # A partially installed / broken praisonai_tools can raise more than
            # ImportError (AttributeError, SyntaxError, ...). Never crash resolution.
            _praisonai_tools_available = False

    return None


def _available_tool_names() -> List[str]:
    """Best-effort catalogue of known tool names for suggestions."""
    names: set = set()

    try:
        from .registry import get_registry

        names.update(get_registry().list_tools())
    except Exception:
        pass

    try:
        from . import TOOL_MAPPINGS

        names.update(TOOL_MAPPINGS.keys())
    except Exception:
        pass

    global _praisonai_tools_available
    if _praisonai_tools_available is None:
        _praisonai_tools_available = importlib.util.find_spec("praisonai_tools") is not None
    if _praisonai_tools_available:
        try:
            import praisonai_tools

            names.update(getattr(praisonai_tools, "__all__", []) or [])
        except Exception:
            pass

    return sorted(names)


def _closest_names(name: str, limit: int = 3) -> List[str]:
    """Return the closest known tool names to ``name``."""
    return difflib.get_close_matches(name, _available_tool_names(), n=limit, cutoff=0.6)


def _format_unknown(unknown: List[str], suggestions: Dict[str, List[str]]) -> str:
    parts = []
    for name in unknown:
        near = suggestions.get(name) or []
        if near:
            hint = " Did you mean {}?".format(" or ".join(repr(s) for s in near))
        else:
            hint = ""
        parts.append("Unknown tool {!r}.{} Run 'praisonai tools list'.".format(name, hint))
    return " ".join(parts)


def _default_report(unknown: List[str], suggestions: Dict[str, List[str]]) -> None:
    """User-visible (not log-only) diagnostic for unresolved tool names."""
    logger.warning("%s", _format_unknown(unknown, suggestions))


def resolve_tool_names(
    names: List[str],
    *,
    strict: Optional[bool] = None,
    on_unknown: Optional[Callable[[List[str], Dict[str, List[str]]], None]] = None,
) -> List[Any]:
    """Resolve tool name strings to callables/instances.

    Args:
        names: Tool name strings to resolve.
        strict: If True, raise ``ToolResolutionError`` when any name is unknown.
            Defaults to the ``PRAISONAI_STRICT_TOOLS`` environment variable
            (falsey by default for backward compatibility).
        on_unknown: Optional callback ``(unknown, suggestions)`` invoked for
            unresolved names in non-strict mode instead of the default report.
    """
    if strict is None:
        strict = os.getenv("PRAISONAI_STRICT_TOOLS", "").strip().lower() in ("1", "true", "yes")

    resolved: List[Any] = []
    unknown: List[str] = []
    for name in names:
        tool = resolve_tool_name(name)
        if tool is not None:
            resolved.append(tool)
        else:
            unknown.append(name)

    if unknown:
        suggestions = {name: _closest_names(name) for name in unknown}
        if strict:
            raise ToolResolutionError(unknown=unknown, suggestions=suggestions)
        (on_unknown or _default_report)(unknown, suggestions)

    return resolved
