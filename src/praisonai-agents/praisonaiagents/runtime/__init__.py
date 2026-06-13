"""
Runtime Selection and Registry for Agent Harnesses.

Implements auto runtime selection based on provider/model support and priority,
following AGENTS.md protocol-driven design patterns.

Entry Points:
    resolve_runtime() - Select best runtime for provider/model pair
    register_runtime() - Register new runtime factory
    list_runtimes() - List available runtime IDs

Example:
    # Auto selection
    runtime = resolve_runtime(provider="openai", model="gpt-4", mode="auto")
    
    # Explicit selection  
    runtime = resolve_runtime(provider="openai", model="gpt-4", mode="praisonai")
    
    # Register custom runtime
    register_runtime("custom", CustomRuntimeFactory())
"""

from .protocols import AgentRuntimeProtocol
from .registry import register_runtime, list_runtimes
from .resolve import resolve_runtime

__all__ = [
    "AgentRuntimeProtocol",
    "resolve_runtime", 
    "register_runtime",
    "list_runtimes"
]