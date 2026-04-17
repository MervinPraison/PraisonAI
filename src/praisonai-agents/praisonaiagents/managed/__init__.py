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
    SessionInfo,
)

# Lazy re-export of ManagedBackendProtocol from agent.protocols
# Following AGENTS.md protocol-driven design principles
def __getattr__(name: str):
    if name == "ManagedBackendProtocol":
        from ..agent.protocols import ManagedBackendProtocol
        return ManagedBackendProtocol
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

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
    "SessionInfo",
    "ManagedBackendProtocol",  # Lazy re-export from agent.protocols
]
