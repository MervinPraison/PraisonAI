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
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Union, TYPE_CHECKING
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
    model_config: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate model reference."""
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.provider:
            raise ValueError("provider is required")


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
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate tool schema."""
        if not self.name:
            raise ValueError("Tool name is required")
        if not self.description:
            raise ValueError("Tool description is required")


@dataclass(frozen=True)
class TranscriptWindow:
    """
    Immutable transcript window for a turn.
    
    Contains the conversation history slice to be included in the current
    turn, with token budgeting and context optimization applied.
    """
    messages: List[Dict[str, Any]]
    total_tokens: int = 0
    system_prompt: Optional[str] = None
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate transcript window."""
        if not isinstance(self.messages, list):
            raise ValueError("messages must be a list")


@dataclass(frozen=True)
class DeliveryChannels:
    """
    Delivery channels for runtime execution results.
    
    Encapsulates streaming handles, callbacks, and output formatting
    configuration for the current turn.
    """
    stream_emitter: Optional[StreamEventEmitter] = None
    output_formatter: Optional[Any] = None
    callbacks: List[Any] = field(default_factory=list)
    async_callbacks: List[Any] = field(default_factory=list)
    enable_streaming: bool = False
    enable_metrics: bool = False
    
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
    trace_metadata: Dict[str, Any] = field(default_factory=dict)


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
    tools: List[ToolSchema]
    transcript: TranscriptWindow
    delivery: DeliveryChannels
    correlation: SessionCorrelation
    runtime_mode: RuntimeMode = RuntimeMode.SYNC
    turn_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Validate the prepared turn context."""
        if not isinstance(self.tools, list):
            raise ValueError("tools must be a list")
        
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


@runtime_checkable
class TurnRuntimeProtocol(Protocol):
    """
    Protocol for turn-based runtime execution.
    
    This protocol defines the interface that runtimes must implement to
    execute prepared turn contexts. It standardizes the execution contract
    across different runtime types (native, plugin, managed, etc.).
    
    Example:
        ```python
        class MyRuntime:
            async def run_turn(self, context: PreparedTurnContext) -> str:
                # Execute the turn using the prepared context
                return "response"
        
        # Use with prepared context
        context = PreparedTurnContext(...)
        runtime = MyRuntime()
        result = await runtime.run_turn(context)
        ```
    """
    
    async def run_turn(self, context: PreparedTurnContext) -> str:
        """
        Execute a single turn using the prepared context.
        
        This is the main execution entry point for all runtime types.
        The context is immutable and contains all necessary configuration
        for the turn execution.
        
        Args:
            context: The prepared turn context containing model, tools,
                    transcript, delivery channels, and correlation IDs
                    
        Returns:
            The agent's response as a string
            
        Raises:
            RuntimeError: If execution fails
            ValueError: If context is invalid or incompatible
        """
        ...
    
    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """
        Check if this runtime supports the given execution mode.
        
        Args:
            mode: The runtime mode to check
            
        Returns:
            True if the mode is supported, False otherwise
        """
        ...
    
    def get_supported_modes(self) -> List[RuntimeMode]:
        """
        Get all runtime modes supported by this implementation.
        
        Returns:
            List of supported RuntimeMode values
        """
        ...


@runtime_checkable  
class TurnContextBuilderProtocol(Protocol):
    """
    Protocol for building PreparedTurnContext instances.
    
    This protocol defines the interface for context builders that prepare
    turn contexts from agent configuration and request parameters.
    """
    
    def build_context(
        self,
        agent: AgentProtocol,
        prompt: str,
        **kwargs: Any
    ) -> PreparedTurnContext:
        """
        Build a prepared turn context from agent and request.
        
        Args:
            agent: The agent instance
            prompt: The user prompt for this turn
            **kwargs: Additional request parameters
            
        Returns:
            A prepared turn context ready for execution
        """
        ...


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