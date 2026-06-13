"""
Runtime Protocol for Agent Harness Selection.

Defines the interface for runtime harnesses that can host agent execution
with provider/model-specific support and priority-based selection.
"""

from __future__ import annotations
from typing import Protocol, Any, Dict, Optional, runtime_checkable


@runtime_checkable
class AgentRuntimeProtocol(Protocol):
    """Protocol for agent runtime harnesses with auto-selection support.
    
    Extends runtime capabilities with provider/model matching and priority-based
    selection for auto mode. Implementations should handle agent execution
    lifecycle with proper provider/model compatibility.
    
    Example:
        class CustomRuntime:
            def supports(self, provider: str, model: str) -> bool:
                return provider == "openai" and model.startswith("gpt-")
                
            def selection_priority(self) -> int:
                return 100  # Higher priority than default praisonai (50)
                
            async def execute_agent(self, config): ...
    """

    def supports(self, provider: str, model: str) -> bool:
        """Check if this runtime supports the provider/model combination.
        
        Args:
            provider: LLM provider name (e.g., "openai", "anthropic", "google")
            model: Model name (e.g., "gpt-4", "claude-3-opus")
            
        Returns:
            True if this runtime can handle this provider/model pair
        """
        ...

    def selection_priority(self) -> int:
        """Priority for auto-selection (lower values = higher priority).
        
        Built-in praisonai runtime uses priority 50. Custom runtimes should
        use values relative to this baseline. Lower numbers take precedence
        during tie-breaking in auto mode.
        
        Returns:
            Integer priority value (lower = preferred)
        """
        ...

    async def execute_agent(
        self, 
        config: Dict[str, Any],
        **kwargs
    ) -> Any:
        """Execute agent with runtime-specific implementation.
        
        Args:
            config: Agent configuration including model, tools, system prompt
            **kwargs: Additional runtime-specific parameters
            
        Returns:
            Runtime-specific result object
        """
        ...

    async def cleanup(self) -> None:
        """Clean up runtime resources.
        
        Called when runtime is no longer needed. Implementations should
        release any held resources, close connections, etc.
        """
        ...

    @property
    def runtime_id(self) -> str:
        """Unique identifier for this runtime.
        
        Used for explicit runtime selection and logging. Should be
        unique across all registered runtimes.
        """
        ...

    @property 
    def is_available(self) -> bool:
        """Whether this runtime is currently available.
        
        Returns False if runtime has missing dependencies, configuration
        issues, or is temporarily unavailable.
        """
        ...