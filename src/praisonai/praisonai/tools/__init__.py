"""
PraisonAI CLI Tools.

This module provides CLI-specific tools that complement the core praisonaiagents tools.
These tools are optimized for interactive CLI workflows.
"""

__all__ = [
    "multiedit",
    "glob_files",
    "grep_search",
    "tts_tool",
    "stt_tool",
    "create_tts_tool",
    "create_stt_tool",
    "get_kanban_tools",
    "KANBAN_TOOLS",
]

from .._lazy_cache import lazy_get

_LAZY_ATTRS = {
    "multiedit":        lambda: __import__("praisonai.tools.multiedit", fromlist=["multiedit"]).multiedit,
    "glob_files":       lambda: __import__("praisonai.tools.glob_tool", fromlist=["glob_files"]).glob_files,
    "grep_search":      lambda: __import__("praisonai.tools.grep_tool", fromlist=["grep_search"]).grep_search,
    "tts_tool":         lambda: __import__("praisonai.tools.audio", fromlist=["tts_tool"]).tts_tool,
    "stt_tool":         lambda: __import__("praisonai.tools.audio", fromlist=["stt_tool"]).stt_tool,
    "create_tts_tool":  lambda: __import__("praisonai.tools.audio", fromlist=["create_tts_tool"]).create_tts_tool,
    "create_stt_tool":  lambda: __import__("praisonai.tools.audio", fromlist=["create_stt_tool"]).create_stt_tool,
    "get_kanban_tools": lambda: __import__("praisonai.tools.kanban_tools", fromlist=["get_kanban_tools"]).get_kanban_tools,
    "KANBAN_TOOLS":     lambda: __import__("praisonai.tools.kanban_tools", fromlist=["KANBAN_TOOLS"]).KANBAN_TOOLS,
}


def __getattr__(name: str):
    """Lazy load tools."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = lazy_get(f"tools:{name}", _LAZY_ATTRS[name])
    # Bind on the package: importing ``.multiedit`` sets the submodule as the
    # ``multiedit`` attribute, which would otherwise shadow the function.
    globals()[name] = value
    return value
