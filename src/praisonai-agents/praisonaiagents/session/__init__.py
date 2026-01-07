"""
Session persistence module for PraisonAI Agents.

Provides automatic session persistence with zero configuration.
When a session_id is provided to an Agent, conversation history
is automatically persisted to disk and restored on subsequent runs.

Usage:
    from praisonaiagents import Agent
    
    # With session persistence (auto-enabled)
    agent = Agent(
        name="Assistant",
        session_id="my-session-123"
    )
    agent.start("Hello")
    
    # Later, new process - history is restored
    agent = Agent(
        name="Assistant", 
        session_id="my-session-123"
    )
    agent.start("What did I say before?")  # Remembers!

Default storage: ~/.praison/sessions/{session_id}.json
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import DefaultSessionStore, SessionMessage, SessionData

# Lazy loading for zero import overhead
_module_cache = {}


def __getattr__(name: str):
    """Lazy load session components."""
    if name in _module_cache:
        return _module_cache[name]
    
    if name == "Session":
        from .api import Session
        _module_cache[name] = Session
        return Session
    
    if name == "DefaultSessionStore":
        from .store import DefaultSessionStore
        _module_cache[name] = DefaultSessionStore
        return DefaultSessionStore
    
    if name == "SessionMessage":
        from .store import SessionMessage
        _module_cache[name] = SessionMessage
        return SessionMessage
    
    if name == "SessionData":
        from .store import SessionData
        _module_cache[name] = SessionData
        return SessionData
    
    if name == "get_default_session_store":
        from .store import get_default_session_store
        _module_cache[name] = get_default_session_store
        return get_default_session_store
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Session",
    "DefaultSessionStore",
    "SessionMessage", 
    "SessionData",
    "get_default_session_store",
]
