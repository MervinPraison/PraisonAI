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
]

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load tools."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "multiedit":
        from .multiedit import multiedit
        _lazy_cache[name] = multiedit
        return multiedit
    
    if name == "glob_files":
        from .glob_tool import glob_files
        _lazy_cache[name] = glob_files
        return glob_files
    
    if name == "grep_search":
        from .grep_tool import grep_search
        _lazy_cache[name] = grep_search
        return grep_search
    
    if name == "tts_tool":
        from .audio import tts_tool
        _lazy_cache[name] = tts_tool
        return tts_tool
    
    if name == "stt_tool":
        from .audio import stt_tool
        _lazy_cache[name] = stt_tool
        return stt_tool
    
    if name == "create_tts_tool":
        from .audio import create_tts_tool
        _lazy_cache[name] = create_tts_tool
        return create_tts_tool
    
    if name == "create_stt_tool":
        from .audio import create_stt_tool
        _lazy_cache[name] = create_stt_tool
        return create_stt_tool
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
