"""Agent Runtime protocols and data structures.

Protocol-driven design following AGENTS.md:
- Lightweight protocols only (no implementations)
- Dataclasses for configuration
- Async-first with proper typing
"""

from dataclasses import dataclass, field
from typing import Protocol, AsyncIterator, Optional, List, Dict, Any, runtime_checkable


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