"""
Unified Interactive Core for PraisonAI CLI.

This module provides a single core runtime that powers all interactive modes:
- `praisonai run --interactive`
- `praisonai chat`
- `praisonai tui launch`

All UIs consume the same event model; only rendering differs.
"""

__all__ = [
    "InteractiveCore",
    "InteractiveConfig",
    "InteractiveEvent",
    "InteractiveEventType",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalDecision",
]

# Lazy imports to avoid loading heavy dependencies on import
_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load interactive components."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "InteractiveCore":
        from .core import InteractiveCore
        _lazy_cache[name] = InteractiveCore
        return InteractiveCore
    
    if name == "InteractiveConfig":
        from .config import InteractiveConfig
        _lazy_cache[name] = InteractiveConfig
        return InteractiveConfig
    
    if name in ("InteractiveEvent", "InteractiveEventType", "ApprovalRequest", 
                "ApprovalResponse", "ApprovalDecision"):
        from . import events
        obj = getattr(events, name)
        _lazy_cache[name] = obj
        return obj
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
