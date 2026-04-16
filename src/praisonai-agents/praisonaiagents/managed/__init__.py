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
    "ManagedBackendProtocol",
]


def __getattr__(name: str):
    """Lazy import for heavy dependencies."""
    if name == "ManagedBackendProtocol":
        from ..agent.protocols import ManagedBackendProtocol
        return ManagedBackendProtocol
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
