"""
Runtime Protocols for PraisonAI Agents.

This module defines the protocol interfaces that runtime implementations
must implement. These protocols standardize the execution contract
across different runtime types (native, plugin, managed, etc.).
"""

from __future__ import annotations

from typing import Any, List, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from .turn_context import PreparedTurnContext, RuntimeMode
    from ..agent.protocols import AgentProtocol


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