"""
Registry for web search providers.

Maps search provider names to their tool classes (lazy-loaded).
Extensible: third-party search providers can register via entry points.
"""

from __future__ import annotations

from ..._registry import PluginRegistry


def _duckduckgo_loader():
    from praisonai_tools import DuckDuckGoTool
    return DuckDuckGoTool


def _tavily_loader():
    from praisonai_tools import TavilyTool
    return TavilyTool


def _serper_loader():
    from praisonai_tools import SerperTool
    return SerperTool


# Built-in search providers with lazy loading
_BUILTIN_SEARCH = {
    "duckduckgo": _duckduckgo_loader,
    "tavily": _tavily_loader,
    "serper": _serper_loader,
}


class SearchProviderRegistry(PluginRegistry):
    """Registry for web search providers."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.tools.search",
            builtins=_BUILTIN_SEARCH
        )