"""
UI Integrations for PraisonAI Agents

This module provides UI protocol integrations for exposing PraisonAI Agents
via various frontend protocols.

Available integrations:
- agui: AG-UI (Agent-User Interface) protocol for CopilotKit and compatible frontends
- a2a: Agent-to-Agent protocol
- a2ui: Agent-to-UI protocol

This module uses lazy loading to minimize import time.
"""

# Module-level cache for lazy-loaded classes
_lazy_cache = {}


def __getattr__(name):
    """Lazy load UI classes to avoid importing heavy dependencies at module load time."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "AGUI":
        from praisonaiagents.ui.agui import AGUI
        _lazy_cache[name] = AGUI
        return AGUI
    elif name == "A2A":
        from praisonaiagents.ui.a2a import A2A
        _lazy_cache[name] = A2A
        return A2A
    elif name == "A2UI":
        from praisonaiagents.ui.a2ui import A2UI
        _lazy_cache[name] = A2UI
        return A2UI
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AGUI", "A2A", "A2UI"]
