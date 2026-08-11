"""
Managed Agent Events and Protocols for PraisonAI Agents.

Provider-agnostic event types for managed agent backends.
These are lightweight dataclasses — no heavy dependencies.

Heavy implementations (LocalManagedAgent, AnthropicManagedAgent)
live in the praisonai wrapper package.
"""

from .events import (
    ManagedEvent,
    AgentMessageEvent,
    ToolUseEvent,
    CustomToolUseEvent,
    ToolConfirmationEvent,
    SessionIdleEvent,
    SessionErrorEvent,
    SessionRunningEvent,
    UsageEvent,
)

from .protocols import (
    ComputeProviderProtocol,
    ComputeConfig,
    InstanceInfo,
    InstanceStatus,
    ManagedRuntimeProtocol,
    SupportsCapture,
    load_environment_definition,
    find_environment_definition,
    definition_hash,
    capture_key,
)

__all__ = [
    "ManagedEvent",
    "AgentMessageEvent",
    "ToolUseEvent",
    "CustomToolUseEvent",
    "ToolConfirmationEvent",
    "SessionIdleEvent",
    "SessionErrorEvent",
    "SessionRunningEvent",
    "UsageEvent",
    "ComputeProviderProtocol",
    "ComputeConfig",
    "InstanceInfo",
    "InstanceStatus",
    "ManagedRuntimeProtocol",
    "ManagedBackendProtocol",
    "SupportsCapture",
    "load_environment_definition",
    "find_environment_definition",
    "definition_hash",
    "capture_key",
]


def __getattr__(name: str):
    """Lazy import ManagedBackendProtocol to keep module lightweight."""
    if name == "ManagedBackendProtocol":
        from ..agent.protocols import ManagedBackendProtocol
        return ManagedBackendProtocol
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
