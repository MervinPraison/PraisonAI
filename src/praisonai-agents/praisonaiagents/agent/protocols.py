"""
Agent Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for agent implementations.
This enables:
- Mocking agents in tests without real LLM calls
- Creating custom agent implementations
- Type checking with static analyzers

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Optional, Any, Dict, List


@runtime_checkable
class AgentProtocol(Protocol):
    """
    Minimal Protocol for agent implementations.
    
    This defines the essential interface that any agent must provide.
    It enables proper mocking and testing without real LLM dependencies.
    
    Example:
        ```python
        # Create a mock agent for testing
        class MockAgent:
            @property
            def name(self) -> str:
                return "TestAgent"
            
            def chat(self, prompt: str, **kwargs) -> str:
                return "Mock response"
            
            async def achat(self, prompt: str, **kwargs) -> str:
                return "Async mock response"
        
        # Use in tests
        agent: AgentProtocol = MockAgent()
        result = agent.chat("Hello")
        ```
    """
    
    @property
    def name(self) -> str:
        """Agent's name identifier."""
        ...
    
    def chat(self, prompt: str, **kwargs) -> str:
        """
        Synchronous chat with the agent.
        
        Args:
            prompt: The user prompt or message
            **kwargs: Additional optional parameters (temperature, tools, etc.)
            
        Returns:
            The agent's response as a string
        """
        ...
    
    async def achat(self, prompt: str, **kwargs) -> str:
        """
        Asynchronous chat with the agent.
        
        Args:
            prompt: The user prompt or message
            **kwargs: Additional optional parameters (temperature, tools, etc.)
            
        Returns:
            The agent's response as a string
        """
        ...


@runtime_checkable
class RunnableAgentProtocol(AgentProtocol, Protocol):
    """
    Extended Protocol for agents that support run/start methods.
    
    This extends AgentProtocol with the run/start interface used
    by the Agent class for task execution.
    """
    
    def run(self, prompt: str, **kwargs) -> str:
        """Run the agent with a prompt (alias for chat in most cases)."""
        ...
    
    def start(self, prompt: str, **kwargs) -> str:
        """Start the agent with a prompt."""
        ...
    
    async def arun(self, prompt: str, **kwargs) -> str:
        """Async run the agent with a prompt."""
        ...
    
    async def astart(self, prompt: str, **kwargs) -> str:
        """Async start the agent with a prompt."""
        ...


@runtime_checkable
class ToolAwareAgentProtocol(AgentProtocol, Protocol):
    """
    Protocol for agents that support tools.
    
    This extends AgentProtocol with tool-related properties.
    """
    
    @property
    def tools(self) -> List[Any]:
        """List of tools available to the agent."""
        ...


@runtime_checkable  
class MemoryAwareAgentProtocol(AgentProtocol, Protocol):
    """
    Protocol for agents that support memory.
    
    This extends AgentProtocol with memory-related properties.
    """
    
    @property
    def chat_history(self) -> List[Dict[str, Any]]:
        """The agent's conversation history."""
        ...
    
    def clear_history(self) -> None:
        """Clear the agent's conversation history."""
        ...


# Composite protocol for fully-featured agents
@runtime_checkable
class FullAgentProtocol(RunnableAgentProtocol, ToolAwareAgentProtocol, MemoryAwareAgentProtocol, Protocol):
    """
    Complete Protocol for full-featured agents.
    
    This combines all agent protocol features for agents that support
    the full interface (chat, run, tools, memory).
    """
    pass


@runtime_checkable
class ContextEngineerProtocol(Protocol):
    """
    Protocol for Context Engineering agents.
    
    Defines the interface for agents that perform codebase analysis,
    PRP (Product Requirements Prompt) generation, and implementation planning.
    
    This protocol enables:
    - Lightweight core with protocol definition only
    - Heavy implementations in wrapper/tools
    - Easy mocking for tests
    
    Example:
        ```python
        class MockContextEngineer:
            def analyze_codebase(self, path: str) -> Dict[str, Any]:
                return {"project": path, "patterns": []}
            
            def generate_prp(self, request: str, analysis: Dict = None) -> str:
                return f"PRP for: {request}"
            
            async def aanalyze_codebase(self, path: str) -> Dict[str, Any]:
                return await self.analyze_codebase(path)
        ```
    """
    
    def analyze_codebase(self, project_path: str) -> Dict[str, Any]:
        """
        Analyze a codebase and extract patterns, structure, and conventions.
        
        Args:
            project_path: Path to the project directory
            
        Returns:
            Analysis results including patterns, architecture, conventions
        """
        ...
    
    def generate_prp(
        self, 
        feature_request: str, 
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a Product Requirements Prompt (PRP) for a feature.
        
        Args:
            feature_request: Description of the feature to implement
            context_analysis: Optional codebase analysis to include
            
        Returns:
            Comprehensive PRP document as string
        """
        ...
    
    def create_implementation_blueprint(
        self,
        feature_request: str,
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a step-by-step implementation blueprint.
        
        Args:
            feature_request: Description of the feature
            context_analysis: Optional codebase analysis
            
        Returns:
            Blueprint with implementation steps, files to modify, etc.
        """
        ...
    
    async def aanalyze_codebase(self, project_path: str) -> Dict[str, Any]:
        """Async version of analyze_codebase."""
        ...
    
    async def agenerate_prp(
        self,
        feature_request: str,
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """Async version of generate_prp."""
        ...


__all__ = [
    'AgentProtocol',
    'RunnableAgentProtocol', 
    'ToolAwareAgentProtocol',
    'MemoryAwareAgentProtocol',
    'FullAgentProtocol',
    'ContextEngineerProtocol',
]
