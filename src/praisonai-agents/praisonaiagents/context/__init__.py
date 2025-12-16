"""
Context module for PraisonAI Agents.

This module provides context retrieval capabilities including:
- Fast Context: Rapid parallel code search subagent
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "FastContext",
    "FastContextResult",
    "FileMatch",
    "LineRange",
]
