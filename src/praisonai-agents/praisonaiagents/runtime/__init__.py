"""
Runtime module for PraisonAI Agents.

Provides runtime-scoped tool result middleware for plugin harnesses.
Plugin harnesses return tool results in vendor-specific shapes, and this 
middleware normalizes them before they reach hooks and memory adapters.

Key Components:
- RuntimeToolResultMiddleware: Protocol for normalizing tool results
- RuntimeRegistry: Registry for managing runtime-specific middleware
- NormalizedToolResult: Standardized result format

Usage:
    from praisonaiagents.runtime import RuntimeRegistry, RuntimeToolResultMiddleware
    
    # Register middleware for a specific runtime
    registry = RuntimeRegistry()
    registry.register("my_runtime", MyMiddleware())
    
    # Use with agent
    agent = Agent(
        name="MyAgent",
        runtime_registry=registry
    )
"""

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Core protocols
    "RuntimeToolResultMiddleware",
    "NormalizedToolResult", 
    "RuntimeRegistry",
    # Middleware context
    "MiddlewareContext",
    # Registry management
    "get_default_registry",
    "register_middleware",
    "get_middleware",
]

# Grouped lazy imports for efficient loading
_LAZY_GROUPS = {
    'middleware': {
        'RuntimeToolResultMiddleware': ('praisonaiagents.runtime.middleware', 'RuntimeToolResultMiddleware'),
        'NormalizedToolResult': ('praisonaiagents.runtime.middleware', 'NormalizedToolResult'),
        'MiddlewareContext': ('praisonaiagents.runtime.middleware', 'MiddlewareContext'),
    },
    'registry': {
        'RuntimeRegistry': ('praisonaiagents.runtime.registry', 'RuntimeRegistry'),
        'get_default_registry': ('praisonaiagents.runtime.registry', 'get_default_registry'),
        'register_middleware': ('praisonaiagents.runtime.registry', 'register_middleware'),
        'get_middleware': ('praisonaiagents.runtime.registry', 'get_middleware'),
    },
}

# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)