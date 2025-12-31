"""
TUI Screens for PraisonAI.

Screen definitions for different views in the TUI application.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import MainScreen
    from .queue import QueueScreen
    from .settings import SettingsScreen
    from .session import SessionScreen

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load screens."""
    global _lazy_cache
    
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "MainScreen":
        from .main import MainScreen
        _lazy_cache[name] = MainScreen
        return MainScreen
    elif name == "QueueScreen":
        from .queue import QueueScreen
        _lazy_cache[name] = QueueScreen
        return QueueScreen
    elif name == "SettingsScreen":
        from .settings import SettingsScreen
        _lazy_cache[name] = SettingsScreen
        return SettingsScreen
    elif name == "SessionScreen":
        from .session import SessionScreen
        _lazy_cache[name] = SessionScreen
        return SessionScreen
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MainScreen",
    "QueueScreen",
    "SettingsScreen",
    "SessionScreen",
]
