"""
Frontend implementations for InteractiveCore.

Each frontend subscribes to InteractiveCore events and renders them
using its specific UI framework.
"""

__all__ = [
    "RichFrontend",
    "TextualFrontend",
]

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load frontends."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "RichFrontend":
        from .rich_frontend import RichFrontend
        _lazy_cache[name] = RichFrontend
        return RichFrontend
    
    if name == "TextualFrontend":
        from .textual_frontend import TextualFrontend
        _lazy_cache[name] = TextualFrontend
        return TextualFrontend
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
