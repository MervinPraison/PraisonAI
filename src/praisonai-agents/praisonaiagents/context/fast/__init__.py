"""
Fast Context module for rapid parallel code search.

This module implements a specialized subagent that retrieves relevant code
from a codebase using parallel tool calls, similar to Windsurf's Fast Context.

Key features:
- Parallel tool execution (up to 8 concurrent calls)
- Limited serial turns (max 4) for fast response
- Restricted tool set (grep, glob, read) for safety
- Returns files + line ranges (no summarization)
"""

# Lazy imports to avoid impacting package load time
def __getattr__(name):
    """Lazy import to avoid impacting package performance."""
    if name == "FastContext":
        from praisonaiagents.context.fast.fast_context import FastContext
        return FastContext
    elif name == "FastContextResult":
        from praisonaiagents.context.fast.result import FastContextResult
        return FastContextResult
    elif name == "FileMatch":
        from praisonaiagents.context.fast.result import FileMatch
        return FileMatch
    elif name == "LineRange":
        from praisonaiagents.context.fast.result import LineRange
        return LineRange
    elif name == "FastContextAgent":
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        return FastContextAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "FastContext",
    "FastContextResult",
    "FileMatch",
    "LineRange",
    "FastContextAgent",
]
