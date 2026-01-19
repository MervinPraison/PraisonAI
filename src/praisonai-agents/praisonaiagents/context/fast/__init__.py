"""
Fast Context module for rapid parallel code search.

This module implements a specialized subagent that retrieves relevant code
from a codebase using parallel tool calls, similar to Windsurf's Fast Context.

Key features:
- Parallel tool execution (up to 8 concurrent calls)
- Limited serial turns (max 4) for fast response
- Restricted tool set (grep, glob, read) for safety
- Returns files + line ranges (no summarization)

Optional optimizations (no performance impact when disabled):
- Ripgrep backend: Use `search_backend='ripgrep'` for faster grep
- Async file I/O: Uses aiofiles if installed
- Incremental indexing: Use `enable_indexing=True`
- Context compression: Use `compression='truncate'` or `compression='smart'`
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
    # New optimization exports
    elif name == "get_search_backend":
        from praisonaiagents.context.fast.search_backends import get_search_backend
        return get_search_backend
    elif name == "PythonSearchBackend":
        from praisonaiagents.context.fast.search_backends import PythonSearchBackend
        return PythonSearchBackend
    elif name == "RipgrepBackend":
        from praisonaiagents.context.fast.search_backends import RipgrepBackend
        return RipgrepBackend
    elif name == "FileIndex":
        from praisonaiagents.context.fast.index_manager import FileIndex
        return FileIndex
    elif name == "get_compressor":
        from praisonaiagents.context.fast.compressor import get_compressor
        return get_compressor
    elif name == "TruncateCompressor":
        from praisonaiagents.context.fast.compressor import TruncateCompressor
        return TruncateCompressor
    elif name == "SmartCompressor":
        from praisonaiagents.context.fast.compressor import SmartCompressor
        return SmartCompressor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "FastContext",
    "FastContextResult",
    "FileMatch",
    "LineRange",
    "FastContextAgent",
    # Optimization exports
    "get_search_backend",
    "PythonSearchBackend", 
    "RipgrepBackend",
    "FileIndex",
    "get_compressor",
    "TruncateCompressor",
    "SmartCompressor",
]

