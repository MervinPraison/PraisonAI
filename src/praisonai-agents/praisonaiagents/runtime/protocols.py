"""
Runtime Protocols for PraisonAI Agents.

This module defines the protocol interfaces that runtime implementations
must implement. These protocols standardize the execution contract
across different runtime types (native, plugin, managed, etc.).

Includes both turn-context protocols and agent runtime protocols to support
different execution patterns, along with capability reporting protocols 
for runtime compatibility validation.

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
    from .capabilities import RuntimeCapabilityMatrix
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


# Agent runtime protocols and dataclasses

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
    """
    Protocol that all agent runtime implementations must follow.
    
    This protocol defines the interface for different runtime environments:
    - Native runtime (built-in praisonai runtime)
    - Plugin harness runtimes (external CLI tools, docker containers)
    - Managed service runtimes (Anthropic, E2B, Modal, etc.)
    
    Combines turn-based execution with capability reporting to enable
    both runtime execution and compatibility validation.
    """
    
    @property
    def runtime_name(self) -> str:
        """
        Human-readable name of this runtime implementation.
        
        Examples: "native", "claude-code", "e2b-managed", "docker-harness"
        """
        ...
    
    @property 
    def runtime_version(self) -> str:
        """
        Version string of this runtime implementation.
        
        Used for compatibility tracking and debugging.
        """
        ...
    
    def capabilities(self) -> "RuntimeCapabilityMatrix":
        """
        Report the capability matrix for this runtime.
        
        This is the key method for the capability validation system.
        Each runtime must honestly declare what features it supports
        to enable fail-fast validation at config/selection time.
        
        Returns:
            RuntimeCapabilityMatrix with supported capabilities
        """
        ...
    
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
    
    async def execute_agent(
        self, 
        agent_config: Dict[str, Any], 
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute agent with the given configuration and prompt.
        
        Args:
            agent_config: Agent configuration dict
            prompt: User prompt to process
            **kwargs: Additional execution parameters
            
        Returns:
            Execution result dict with response, metadata, etc.
        """
        ...
    
    async def stream_agent(
        self,
        agent_config: Dict[str, Any],
        prompt: str,
        **kwargs
    ) -> Any:  # AsyncIterator but avoid import
        """
        Execute agent with streaming responses.
        
        Only required if runtime declares streaming_deltas capability.
        
        Args:
            agent_config: Agent configuration dict 
            prompt: User prompt to process
            **kwargs: Additional execution parameters
            
        Yields:
            Streaming response chunks
        """
        ...
    
    async def validate_config(
        self, 
        agent_config: Dict[str, Any]
    ) -> List[str]:
        """
        Validate agent configuration against runtime capabilities.
        
        Args:
            agent_config: Agent configuration to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        ...
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform runtime health check.
        
        Returns:
            Health status dict with status, latency, errors, etc.
        """
        ...


# CliBackendProtocol removed - use the canonical definition from cli_backend.protocols instead
# to avoid duplicate incompatible protocol definitions
