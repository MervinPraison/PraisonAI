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

Default storage: ~/.praisonai/sessions/{session_id}.json
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import DefaultSessionStore, SessionMessage, SessionData
    from .protocols import SessionStoreProtocol
    from .hierarchy import HierarchicalSessionStore, SessionSnapshot, ExtendedSessionData

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
    
    if name == "SessionStoreProtocol":
        from .protocols import SessionStoreProtocol
        _module_cache[name] = SessionStoreProtocol
        return SessionStoreProtocol
    
    if name == "HierarchicalSessionStore":
        from .hierarchy import HierarchicalSessionStore
        _module_cache[name] = HierarchicalSessionStore
        return HierarchicalSessionStore
    
    if name == "get_hierarchical_session_store":
        from .hierarchy import get_hierarchical_session_store
        _module_cache[name] = get_hierarchical_session_store
        return get_hierarchical_session_store
    
    if name == "SessionSnapshot":
        from .hierarchy import SessionSnapshot
        _module_cache[name] = SessionSnapshot
        return SessionSnapshot
    
    if name == "ExtendedSessionData":
        from .hierarchy import ExtendedSessionData
        _module_cache[name] = ExtendedSessionData
        return ExtendedSessionData
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Session",
    "DefaultSessionStore",
    "SessionMessage", 
    "SessionData",
    "get_default_session_store",
    "SessionStoreProtocol",
    "HierarchicalSessionStore",
    "get_hierarchical_session_store",
    "SessionSnapshot",
    "ExtendedSessionData",
]
