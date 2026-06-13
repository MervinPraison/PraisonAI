"""
Runtime resolution system for PraisonAI Agents.

This module provides turn-time runtime resolution for handoffs and sub-agents,
ensuring that model changes and runtime configurations are properly resolved
at execution boundaries rather than construction time.
"""

from .resolve import (
    resolve_runtime, 
    RuntimeProtocol, 
    AgentRuntimeProtocol,
    SessionContext,
    get_runtime_cache, 
    clear_runtime_cache,
    set_global_resolver
)

__all__ = [
    'resolve_runtime',
    'RuntimeProtocol',
    'AgentRuntimeProtocol', 
    'SessionContext',
    'get_runtime_cache',
    'clear_runtime_cache',
    'set_global_resolver'
]