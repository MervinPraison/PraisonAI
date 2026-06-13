""" 
Runtime execution components for PraisonAI agents.

This module provides runtime execution abstractions and protocols for 
standardizing agent execution across different harness types.

Key Components:
- Runtime execution contexts: PreparedTurnContext, TurnRuntimeProtocol  
- Agent runtime registry: AgentRuntimeProtocol, RuntimeRegistry
- Tool result middleware: RuntimeToolResultMiddleware, NormalizedToolResult
- Registry patterns for runtime resolution and middleware management
"""

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Runtime execution contexts
    'PreparedTurnContext',
    'TurnRuntimeProtocol',
    'TurnContextBuilderProtocol',
    'ModelReference',
    'ToolSchema', 
    'TranscriptWindow',
    'DeliveryChannels',
    'SessionCorrelation',
    'RuntimeMode',
    'create_default_model_ref',
    'create_empty_transcript',
    'create_default_delivery',
    'create_session_correlation',
    'DefaultTurnContextBuilder',
    'default_context_builder',
    # Tool result middleware
    "RuntimeToolResultMiddleware",
    "NormalizedToolResult", 
    "MiddlewareContext",
    # Middleware registry management  
    "MiddlewareRegistry",
    "get_default_middleware_registry",
    "register_middleware",
    "get_middleware",
    # Agent runtime APIs
    'AgentRuntimeProtocol',
    'RuntimeConfig', 
    'RuntimeResult',
    'RuntimeDelta',
    'RuntimeRegistry',
    'register_runtime',
    'list_runtimes', 
    'resolve_runtime',
]

# Grouped lazy imports for efficient loading
_LAZY_GROUPS = {
    'turn_context': {
        'PreparedTurnContext': ('praisonaiagents.runtime.turn_context', 'PreparedTurnContext'),
        'ModelReference': ('praisonaiagents.runtime.turn_context', 'ModelReference'),
        'ToolSchema': ('praisonaiagents.runtime.turn_context', 'ToolSchema'),
        'TranscriptWindow': ('praisonaiagents.runtime.turn_context', 'TranscriptWindow'),
        'DeliveryChannels': ('praisonaiagents.runtime.turn_context', 'DeliveryChannels'),
        'SessionCorrelation': ('praisonaiagents.runtime.turn_context', 'SessionCorrelation'),
        'RuntimeMode': ('praisonaiagents.runtime.turn_context', 'RuntimeMode'),
        'create_default_model_ref': ('praisonaiagents.runtime.turn_context', 'create_default_model_ref'),
        'create_empty_transcript': ('praisonaiagents.runtime.turn_context', 'create_empty_transcript'),
        'create_default_delivery': ('praisonaiagents.runtime.turn_context', 'create_default_delivery'),
        'create_session_correlation': ('praisonaiagents.runtime.turn_context', 'create_session_correlation'),
    },
    'protocols': {
        'TurnRuntimeProtocol': ('praisonaiagents.runtime.protocols', 'TurnRuntimeProtocol'),
        'TurnContextBuilderProtocol': ('praisonaiagents.runtime.protocols', 'TurnContextBuilderProtocol'),
        'AgentRuntimeProtocol': ('praisonaiagents.runtime.protocols', 'AgentRuntimeProtocol'),
        'RuntimeConfig': ('praisonaiagents.runtime.protocols', 'RuntimeConfig'),
        'RuntimeResult': ('praisonaiagents.runtime.protocols', 'RuntimeResult'),
        'RuntimeDelta': ('praisonaiagents.runtime.protocols', 'RuntimeDelta'),
    },
    'context_builder': {
        'DefaultTurnContextBuilder': ('praisonaiagents.runtime.context_builder', 'DefaultTurnContextBuilder'),
        'default_context_builder': ('praisonaiagents.runtime.context_builder', 'default_context_builder'),
    },
    'middleware': {
        'RuntimeToolResultMiddleware': ('praisonaiagents.runtime.middleware', 'RuntimeToolResultMiddleware'),
        'NormalizedToolResult': ('praisonaiagents.runtime.middleware', 'NormalizedToolResult'),
        'MiddlewareContext': ('praisonaiagents.runtime.middleware', 'MiddlewareContext'),
    },
    'middleware_registry': {
        'MiddlewareRegistry': ('praisonaiagents.runtime.middleware_registry', 'MiddlewareRegistry'),
        'get_default_middleware_registry': ('praisonaiagents.runtime.middleware_registry', 'get_default_middleware_registry'),
        'register_middleware': ('praisonaiagents.runtime.middleware_registry', 'register_middleware'),
        'get_middleware': ('praisonaiagents.runtime.middleware_registry', 'get_middleware'),
    },
    'registry': {
        'RuntimeRegistry': ('praisonaiagents.runtime.registry', 'RuntimeRegistry'),
        'register_runtime': ('praisonaiagents.runtime.registry', 'register_runtime'),
        'list_runtimes': ('praisonaiagents.runtime.registry', 'list_runtimes'),
        'resolve_runtime': ('praisonaiagents.runtime.registry', 'resolve_runtime'),
    },
}

# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)