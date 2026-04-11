"""
Agent Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for agent implementations.
This enables:
- Mocking agents in tests without real LLM calls
- Creating custom agent implementations
- Type checking with static analyzers

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Optional, Any, AsyncIterator, Dict, List
from dataclasses import dataclass, field


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


@runtime_checkable
class HttpLauncherProtocol(Protocol):
    """
    Protocol for HTTP server launchers.
    
    This defines the interface for launching HTTP servers for agents.
    The core SDK defines the protocol, while heavy implementations
    (FastAPI, uvicorn) live in the wrapper layer.
    
    Example:
        ```python
        class FastAPILauncher:
            def launch(self, agent, path="/", port=8000, host="0.0.0.0", debug=False):
                # FastAPI implementation
                pass
        
        # In Agent class
        launcher: HttpLauncherProtocol = get_http_launcher()
        launcher.launch(self, path, port, host, debug)
        ```
    """
    
    def launch(
        self,
        agent: Any,
        path: str = "/",
        port: int = 8000,
        host: str = "0.0.0.0",
        debug: bool = False
    ) -> None:
        """
        Launch HTTP server for the agent.
        
        Args:
            agent: The agent instance to serve
            path: API endpoint path (default: '/')
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
            debug: Enable debug mode (default: False)
        """
        ...


@runtime_checkable
class McpLauncherProtocol(Protocol):
    """
    Protocol for MCP (Model Context Protocol) server launchers.
    
    This defines the interface for launching MCP servers for agents.
    The core SDK defines the protocol, while heavy implementations
    (FastMCP, uvicorn) live in the wrapper layer.
    """
    
    def launch(
        self,
        agent: Any,
        path: str = "/",
        port: int = 8000,
        host: str = "0.0.0.0",
        debug: bool = False
    ) -> None:
        """
        Launch MCP server for the agent.
        
        Args:
            agent: The agent instance to serve
            path: Base path for MCP endpoints
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
            debug: Enable debug mode (default: False)
        """
        ...


@dataclass
class ManagedBackendConfig:
    """Configuration for managed agent backends.
    
    Portable dataclass that describes *what* to create on the managed
    infrastructure without tying to any provider SDK.
    
    Example::
    
        cfg = ManagedBackendConfig(
            model="claude-sonnet-4-6",
            system="You are a coding assistant.",
            tools=[{"type": "agent_toolset_20260401"}],
            packages={"pip": ["pandas", "numpy"]},
            networking={"type": "unrestricted"},
        )
    """
    # ── Agent fields ──
    name: str = "PraisonAI Managed Agent"
    model: str = "claude-sonnet-4-6"
    system: str = "You are a helpful AI assistant."
    tools: List[Dict[str, Any]] = field(default_factory=lambda: [{"type": "agent_toolset_20260401"}])
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[Dict[str, Any]] = field(default_factory=list)
    callable_agents: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ── Environment fields ──
    env_name: str = "praisonai-env"
    packages: Optional[Dict[str, List[str]]] = None
    networking: Dict[str, Any] = field(default_factory=lambda: {"type": "unrestricted"})
    
    # ── Session fields ──
    session_title: str = "PraisonAI session"
    resources: List[Dict[str, Any]] = field(default_factory=list)
    vault_ids: List[str] = field(default_factory=list)


@runtime_checkable
class ManagedBackendProtocol(Protocol):
    """Protocol for external managed agent backends.
    
    Defines the contract between PraisonAI Agent's delegation layer
    (``execution_mixin._delegate_to_backend``) and any managed agent
    infrastructure provider (Anthropic Managed Agents, etc.).
    
    The Core SDK defines *what* — this protocol.
    The Wrapper implements *how* — the provider-specific adapter.
    
    Lifecycle::
    
        backend = SomeManagedBackend(config=ManagedBackendConfig(...))
        agent = Agent(name="coder", backend=backend)
        result = agent.start("Write a script")  # delegates to backend.execute()
    
    Implementations must handle:
    - Agent/environment/session creation and caching
    - Event streaming (agent.message, agent.tool_use, session.status_idle)
    - Custom tool calls (agent.custom_tool_use → user.custom_tool_result)
    - Tool confirmation (always_ask policy → user.tool_confirmation)
    - Usage tracking (input_tokens, output_tokens)
    - Session reset for multi-turn isolation
    
    Example::
    
        class MockManagedBackend:
            async def execute(self, prompt: str, **kwargs) -> str:
                return "mock response"
            
            async def stream(self, prompt: str, **kwargs):
                yield "mock "
                yield "response"
            
            def reset_session(self) -> None:
                pass
            
            def reset_all(self) -> None:
                pass
        
        assert isinstance(MockManagedBackend(), ManagedBackendProtocol)
    """
    
    async def execute(self, prompt: str, **kwargs) -> str:
        """Execute a prompt on managed infrastructure and return the full response.
        
        This is the primary entry point called by Agent._delegate_to_backend().
        
        Args:
            prompt: The user message to send to the managed agent.
            **kwargs: Provider-specific options (e.g., timeout, metadata).
            
        Returns:
            The agent's complete text response.
        """
        ...
    
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream a prompt response as text chunks.
        
        Yields text fragments as the managed agent produces them.
        Used when Agent is invoked with stream=True.
        
        Args:
            prompt: The user message.
            **kwargs: Provider-specific options.
            
        Yields:
            Text chunks from the agent's response.
        """
        ...
        yield ""  # type: ignore[misc]
    
    def reset_session(self) -> None:
        """Discard the cached session so the next execute() creates a fresh one.
        
        The agent and environment remain cached for reuse.
        """
        ...
    
    def reset_all(self) -> None:
        """Discard all cached state (agent, environment, session, client).
        
        Next execute() call will re-create everything from scratch.
        """
        ...


__all__ = [
    'AgentProtocol',
    'RunnableAgentProtocol', 
    'ToolAwareAgentProtocol',
    'MemoryAwareAgentProtocol',
    'FullAgentProtocol',
    'ContextEngineerProtocol',
    'HttpLauncherProtocol',
    'McpLauncherProtocol',
    'ManagedBackendProtocol',
    'ManagedBackendConfig',
]
