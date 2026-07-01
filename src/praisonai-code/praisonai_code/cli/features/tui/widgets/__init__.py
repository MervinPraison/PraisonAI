"""
TUI Widgets for PraisonAI.

Reusable UI components for the TUI application.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .chat import ChatWidget
    from .composer import ComposerWidget
    from .status import StatusWidget
    from .queue_panel import QueuePanelWidget
    from .tool_panel import ToolPanelWidget

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load widgets."""
    global _lazy_cache
    
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "ChatWidget":
        from .chat import ChatWidget
        _lazy_cache[name] = ChatWidget
        return ChatWidget
    elif name == "ComposerWidget":
        from .composer import ComposerWidget
        _lazy_cache[name] = ComposerWidget
        return ComposerWidget
    elif name == "StatusWidget":
        from .status import StatusWidget
        _lazy_cache[name] = StatusWidget
        return StatusWidget
    elif name == "QueuePanelWidget":
        from .queue_panel import QueuePanelWidget
        _lazy_cache[name] = QueuePanelWidget
        return QueuePanelWidget
    elif name == "ToolPanelWidget":
        from .tool_panel import ToolPanelWidget
        _lazy_cache[name] = ToolPanelWidget
        return ToolPanelWidget
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ChatWidget",
    "ComposerWidget", 
    "StatusWidget",
    "QueuePanelWidget",
    "ToolPanelWidget",
]
