"""
Agent hooks for automatic persistence integration.

Provides wrapper functions to add persistence capabilities to PraisonAI agents
without modifying the core SDK.
"""

from .agent_hooks import (
    wrap_agent_with_persistence,
    PersistentAgent,
    create_persistent_session,
)

__all__ = [
    "wrap_agent_with_persistence",
    "PersistentAgent",
    "create_persistent_session",
]
