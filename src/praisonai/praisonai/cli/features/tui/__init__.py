"""
TUI (Terminal User Interface) for PraisonAI.

Provides an app-like interactive experience with:
- Event-loop driven async UI
- Multi-pane layout (chat, tools, queue, status)
- Streaming output
- Queue management
- Session persistence
- Headless simulation mode for CI/testing

Requires the [tui] extra: pip install praisonai[tui]
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import TUIApp
    from .events import TUIEvent, TUIEventType
    from .orchestrator import TuiOrchestrator, UIStateModel, SimulationRunner
    from .mock_provider import MockProvider, MockProviderConfig

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load TUI components."""
    global _lazy_cache
    
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "TUIApp":
        from .app import TUIApp
        _lazy_cache[name] = TUIApp
        return TUIApp
    elif name == "TUIEvent":
        from .events import TUIEvent
        _lazy_cache[name] = TUIEvent
        return TUIEvent
    elif name == "TUIEventType":
        from .events import TUIEventType
        _lazy_cache[name] = TUIEventType
        return TUIEventType
    elif name == "run_tui":
        from .app import run_tui
        _lazy_cache[name] = run_tui
        return run_tui
    elif name == "TuiOrchestrator":
        from .orchestrator import TuiOrchestrator
        _lazy_cache[name] = TuiOrchestrator
        return TuiOrchestrator
    elif name == "UIStateModel":
        from .orchestrator import UIStateModel
        _lazy_cache[name] = UIStateModel
        return UIStateModel
    elif name == "SimulationRunner":
        from .orchestrator import SimulationRunner
        _lazy_cache[name] = SimulationRunner
        return SimulationRunner
    elif name == "MockProvider":
        from .mock_provider import MockProvider
        _lazy_cache[name] = MockProvider
        return MockProvider
    elif name == "MockProviderConfig":
        from .mock_provider import MockProviderConfig
        _lazy_cache[name] = MockProviderConfig
        return MockProviderConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TUIApp",
    "TUIEvent",
    "TUIEventType",
    "run_tui",
    "TuiOrchestrator",
    "UIStateModel",
    "SimulationRunner",
    "MockProvider",
    "MockProviderConfig",
]
