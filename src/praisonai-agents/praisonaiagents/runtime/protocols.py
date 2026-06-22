"""
Runtime Protocols for PraisonAI Agents.

This module defines the protocol interfaces that runtime implementations
must implement. These protocols standardize the execution contract
across different runtime types (native, plugin, managed, etc.).

Includes both turn-context protocols and agent runtime protocols to support
different execution patterns.

Protocol-driven design following AGENTS.md:
- Lightweight protocols only (no heavy implementations)
- Dataclasses for configuration
- Async-first with proper typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from .turn_context import PreparedTurnContext, RuntimeMode
    from ..agent.protocols import AgentProtocol


# Turn-context protocols from main

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


# Agent runtime protocols and dataclasses from this branch

@dataclass
class RuntimeConfig:
    """Declarative runtime configuration.
    
    Base configuration class for runtime implementations.
    Specific runtimes can extend this for their own config needs.
    """
    # Core runtime identification
    runtime_id: str
    
    # Optional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeResult:
    """Result from runtime execution."""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class RuntimeDelta:
    """Streaming delta from runtime execution."""
    type: str  # "text" | "tool_call" | "thinking" | "error"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AgentRuntimeProtocol(Protocol):
    """Protocol for agent runtime implementations.
    
    Any object implementing these methods can serve as an Agent runtime.
    Follows typing.Protocol pattern from AGENTS.md.
    
    This is a simpler contract than CliBackendProtocol, focused on 
    the minimal interface needed for runtime execution.
    """
    
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Check if this runtime supports the given model reference.
        
        Args:
            model_ref: Optional model reference (e.g., "gpt-4", "claude-3")
            
        Returns:
            True if this runtime can handle the model, False otherwise
        """
        ...
    
    async def run_turn(
        self, 
        prompt: str, 
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Execute a single turn and return result.
        
        Args:
            prompt: User prompt/query
            system_prompt: Optional system prompt
            model_ref: Optional model reference
            **kwargs: Additional runtime-specific options
            
        Returns:
            RuntimeResult with response content and metadata
        """
        ...
    
    async def stream_turn(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream response deltas from runtime execution.
        
        Args:
            prompt: User prompt/query
            **kwargs: Additional options (system_prompt, model_ref, etc.)
            
        Yields:
            RuntimeDelta objects with incremental response content
        """
        ...


@runtime_checkable
class StreamingRuntimeProtocol(Protocol):
    """Extended protocol for runtimes with enhanced streaming capabilities.
    
    Optional protocol that runtimes can implement to indicate support for
    true incremental streaming. This will be the migration path when the
    underlying Agent implementation adds AsyncIterator support.
    
    Example:
        ```python
        # Check if runtime supports enhanced streaming
        if isinstance(runtime, StreamingRuntimeProtocol):
            if runtime.supports_incremental_streaming():
                # Use enhanced streaming
                async for delta in runtime.stream_turn_incremental(prompt):
                    process_delta(delta)
        ```
    """
    
    def supports_incremental_streaming(self) -> bool:
        """Check if this runtime supports true incremental streaming.
        
        Returns:
            True if the runtime can stream incremental deltas,
            False if it only supports single-delta responses
        """
        ...
    
    async def stream_turn_incremental(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream true incremental response deltas.
        
        This method will be called when true streaming is available.
        Unlike the base stream_turn which may return a single delta,
        this guarantees incremental streaming of response chunks.
        
        Args:
            prompt: User prompt/query
            **kwargs: Additional options (system_prompt, model_ref, etc.)
            
        Yields:
            RuntimeDelta objects with incremental response chunks
        """
        ...