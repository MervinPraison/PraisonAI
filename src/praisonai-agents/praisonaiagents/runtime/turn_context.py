"""
Turn Context and Runtime Protocol for PraisonAI Agents.

This module defines the PreparedTurnContext dataclass and TurnRuntimeProtocol
that standardize runtime preparation across different execution paths in the
PraisonAI agent framework.

Design Goals:
- Single immutable plan object passed into runtime run_turn
- Standardize tool assembly, transcript building, and delivery channels
- Eliminate duplication between native loop and plugin harnesses
- Enable consistent metrics and tracing across harness types
- Multi-agent safe: context is per-turn, not stored on shared agent globals
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING, Tuple, Mapping
from types import MappingProxyType
from enum import Enum
import time
import logging

if TYPE_CHECKING:
    from ..agent.protocols import AgentProtocol
    from ..streaming.events import StreamEventEmitter

logger = logging.getLogger(__name__)


class RuntimeMode(Enum):
    """Execution mode for the runtime."""
    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"
    ASYNC_STREAM = "async_stream"


@dataclass(frozen=True)
class ModelReference:
    """
    Immutable reference to a resolved model configuration.
    
    Captures model ID, provider, capabilities, and configuration
    resolved at turn preparation time.
    """
    model_id: str
    provider: str
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_system_prompts: bool = True
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    model_config: Mapping[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate model reference and ensure immutability."""
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.provider:
            raise ValueError("provider is required")
        
        # Make model_config immutable
        if not isinstance(self.model_config, MappingProxyType):
            object.__setattr__(self, 'model_config', MappingProxyType(self.model_config))


@dataclass(frozen=True)
class ToolSchema:
    """
    Normalized tool schema for runtime execution.
    
    Provides a consistent tool representation regardless of source
    (function decorators, OpenAI format, custom tools, etc.).
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    callable: Optional[Any] = None
    source_type: str = "unknown"  # function, openai, custom, etc.
    metadata: Mapping[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate tool schema and ensure immutability."""
        if not self.name:
            raise ValueError("Tool name is required")
        if not self.description:
            raise ValueError("Tool description is required")
        
        # Make metadata immutable
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, 'metadata', MappingProxyType(self.metadata))


@dataclass(frozen=True)
class TranscriptWindow:
    """
    Immutable transcript window for a turn.
    
    Contains the conversation history slice to be included in the current
    turn, with token budgeting and context optimization applied.
    """
    messages: Tuple[Mapping[str, Any], ...]
    total_tokens: int = 0
    system_prompt: Optional[str] = None
    context_metadata: Mapping[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate transcript window and ensure immutability."""
        # Convert to tuple of immutable mappings if needed
        if not isinstance(self.messages, tuple):
            immutable_messages = tuple(
                MappingProxyType(msg) if isinstance(msg, dict) else msg
                for msg in self.messages
            )
            object.__setattr__(self, 'messages', immutable_messages)
        
        # Make context_metadata immutable
        if not isinstance(self.context_metadata, MappingProxyType):
            object.__setattr__(self, 'context_metadata', MappingProxyType(self.context_metadata))


@dataclass(frozen=True)
class DeliveryChannels:
    """
    Delivery channels for runtime execution results.
    
    Encapsulates streaming handles, callbacks, and output formatting
    configuration for the current turn.
    """
    stream_emitter: Optional[StreamEventEmitter] = None
    output_formatter: Optional[Any] = None
    callbacks: Tuple[Any, ...] = field(default_factory=tuple)
    async_callbacks: Tuple[Any, ...] = field(default_factory=tuple)
    enable_streaming: bool = False
    enable_metrics: bool = False
    
    def __post_init__(self):
        """Ensure immutability of list fields."""
        # Convert lists to tuples if needed
        if isinstance(self.callbacks, list):
            object.__setattr__(self, 'callbacks', tuple(self.callbacks))
        if isinstance(self.async_callbacks, list):
            object.__setattr__(self, 'async_callbacks', tuple(self.async_callbacks))
    
    def has_streaming(self) -> bool:
        """Check if streaming is configured and enabled."""
        return self.enable_streaming


@dataclass(frozen=True)
class SessionCorrelation:
    """
    Session correlation identifiers for tracing and debugging.
    
    Provides correlation IDs to track requests across distributed
    agent execution and multi-turn conversations.
    """
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    parent_id: Optional[str] = None
    trace_metadata: Mapping[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Ensure immutability of metadata fields."""
        if not isinstance(self.trace_metadata, MappingProxyType):
            object.__setattr__(self, 'trace_metadata', MappingProxyType(self.trace_metadata))


@dataclass(frozen=True)
class PreparedTurnContext:
    """
    Immutable turn plan object for standardized runtime execution.
    
    This dataclass captures all the context needed for a single agent turn,
    prepared in a preflight step before run_attempt. It eliminates the
    scattered tool assembly and message building across different execution
    paths.
    
    The context is read-only during execution - mutations must go through
    defined hooks only. This ensures consistent behavior across different
    runtime harnesses (native, plugin, managed, etc.).
    
    Attributes:
        model_ref: Resolved model configuration and capabilities
        agent_runtime: The runtime protocol instance to execute with
        tools: Normalized tool schemas for the turn
        transcript: Prepared conversation window for the turn
        delivery: Streaming and output delivery configuration
        correlation: Session and tracing identifiers
        runtime_mode: Execution mode (sync/async/stream)
        turn_metadata: Additional turn-specific metadata
        created_at: Timestamp when context was prepared
    """
    model_ref: ModelReference
    agent_runtime: AgentProtocol
    tools: Tuple[ToolSchema, ...]
    transcript: TranscriptWindow
    delivery: DeliveryChannels
    correlation: SessionCorrelation
    runtime_mode: RuntimeMode = RuntimeMode.SYNC
    turn_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Validate the prepared turn context and ensure immutability."""
        # Convert tools to tuple if needed
        if not isinstance(self.tools, tuple):
            object.__setattr__(self, 'tools', tuple(self.tools))
        
        # Make turn_metadata immutable
        if not isinstance(self.turn_metadata, MappingProxyType):
            object.__setattr__(self, 'turn_metadata', MappingProxyType(self.turn_metadata))
        
        # Validate runtime mode compatibility
        if self.runtime_mode in (RuntimeMode.STREAM, RuntimeMode.ASYNC_STREAM):
            if not self.delivery.has_streaming():
                raise ValueError(
                    f"Runtime mode {self.runtime_mode.value} requires streaming configuration"
                )
        
        # Validate model supports required features
        if self.tools and not self.model_ref.supports_tools:
            logger.warning(
                f"Model {self.model_ref.model_id} does not support tools, "
                f"but {len(self.tools)} tools were provided"
            )
    
    def get_tool_by_name(self, name: str) -> Optional[ToolSchema]:
        """Get a tool by name from the prepared tools."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def has_tools(self) -> bool:
        """Check if any tools are available for this turn."""
        return len(self.tools) > 0
    
    def has_system_prompt(self) -> bool:
        """Check if a system prompt is configured."""
        return self.transcript.system_prompt is not None
    
    def get_message_count(self) -> int:
        """Get the number of messages in the transcript window."""
        return len(self.transcript.messages)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging and debugging."""
        return {
            "model_id": self.model_ref.model_id,
            "provider": self.model_ref.provider,
            "tools_count": len(self.tools),
            "message_count": self.get_message_count(),
            "has_system_prompt": self.has_system_prompt(),
            "runtime_mode": self.runtime_mode.value,
            "streaming_enabled": self.delivery.has_streaming(),
            "session_id": self.correlation.session_id,
            "turn_id": self.correlation.turn_id,
            "created_at": self.created_at,
        }



# Utility functions for context building

def create_default_model_ref(
    model_id: str = "gpt-3.5-turbo",
    provider: str = "openai"
) -> ModelReference:
    """Create a default ModelReference for testing and basic usage."""
    return ModelReference(
        model_id=model_id,
        provider=provider,
        supports_streaming=True,
        supports_tools=True,
        supports_system_prompts=True,
    )


def create_empty_transcript(
    system_prompt: Optional[str] = None
) -> TranscriptWindow:
    """Create an empty transcript window with optional system prompt."""
    return TranscriptWindow(
        messages=[],
        system_prompt=system_prompt,
    )


def create_default_delivery() -> DeliveryChannels:
    """Create default delivery channels with no streaming."""
    return DeliveryChannels(
        enable_streaming=False,
        enable_metrics=False,
    )


def create_session_correlation(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None
) -> SessionCorrelation:
    """Create session correlation with basic IDs."""
    import uuid
    return SessionCorrelation(
        session_id=session_id or f"session-{uuid.uuid4().hex[:8]}",
        turn_id=f"turn-{uuid.uuid4().hex[:8]}",
        agent_id=agent_id,
    )