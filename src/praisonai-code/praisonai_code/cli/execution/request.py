"""
ExecutionRequest - Immutable request for execution.

This is the minimal, immutable request that all execution paths use.
CLI/TUI translate their flags into this structure.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Any


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Minimal, immutable request for execution.
    
    NOT a kitchen-sink of all CLI flags.
    CLI/TUI translate their flags into this.
    
    Attributes:
        prompt: The user prompt to execute
        agent_name: Name of the agent (default: "Assistant")
        agent_instructions: Custom instructions for the agent
        model: LLM model to use (None = use default)
        tools: Tuple of tool callables (immutable)
        stream: Whether to stream the response
    
    Note: This is frozen (immutable) to:
    - Prevent accidental mutation during profiling
    - Enable safe sharing across threads/coroutines
    """
    
    # Required
    prompt: str
    
    # Agent identity (optional, has defaults)
    agent_name: str = "Assistant"
    agent_instructions: Optional[str] = None
    
    # Model (optional, has defaults)
    model: Optional[str] = None  # None = use default
    
    # Tools (optional) - using tuple for immutability
    tools: Tuple[Callable[..., Any], ...] = ()
    
    # Execution mode
    stream: bool = False
    
    def __post_init__(self):
        """Validate request after initialization."""
        if not self.prompt:
            raise ValueError("prompt cannot be empty")
    
    def with_model(self, model: str) -> 'ExecutionRequest':
        """Create a new request with a different model."""
        return ExecutionRequest(
            prompt=self.prompt,
            agent_name=self.agent_name,
            agent_instructions=self.agent_instructions,
            model=model,
            tools=self.tools,
            stream=self.stream,
        )
    
    def with_tools(self, tools: Tuple[Callable[..., Any], ...]) -> 'ExecutionRequest':
        """Create a new request with different tools."""
        return ExecutionRequest(
            prompt=self.prompt,
            agent_name=self.agent_name,
            agent_instructions=self.agent_instructions,
            model=self.model,
            tools=tools,
            stream=self.stream,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "prompt": self.prompt,
            "agent_name": self.agent_name,
            "agent_instructions": self.agent_instructions,
            "model": self.model,
            "tools_count": len(self.tools),
            "stream": self.stream,
        }
