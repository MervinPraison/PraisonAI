"""
External Managed Agent Backends Integration.

Provides integration with external managed agent infrastructures as execution backends,
starting with Anthropic's Managed Agents API. This follows the existing BaseCLIIntegration 
pattern but for managed remote agent services instead of CLI tools.

Features:
- Generic managed agent backend support
- Anthropic Managed Agents API integration
- Session management and event streaming
- Tool mapping from managed to PraisonAI tools
- Async execution with timeout handling

Usage:
    from praisonai.integrations import ManagedAgentIntegration
    
    # Create managed backend
    managed = ManagedAgentIntegration(
        provider="anthropic",
        api_key="your-api-key",
        config={"model": "claude-sonnet-4-6"}
    )
    
    # Execute agent in managed infrastructure
    result = await managed.execute("Create a FastAPI app")
    
    # Use with PraisonAI Agent
    from praisonaiagents import Agent
    agent = Agent(name="coder", backend=managed)
    result = agent.start("Create a FastAPI app")
"""

import asyncio
import json
import os
from typing import AsyncIterator, Dict, Any, Optional, List
from abc import ABC, abstractmethod

# Use existing aiohttp for HTTP requests (no new dependencies)
try:
    import aiohttp
except ImportError:
    aiohttp = None

from .base import BaseCLIIntegration


class ManagedBackendProtocol(ABC):
    """
    Protocol for managed agent backend providers.
    
    Defines the interface that all managed agent providers must implement.
    Follows the protocol-driven design from AGENTS.md.
    """
    
    @abstractmethod
    async def create_agent(self, instructions: str, **config) -> str:
        """Create an agent configuration and return agent_id."""
        pass
    
    @abstractmethod
    async def create_environment(self, **config) -> str:
        """Create an environment and return environment_id."""
        pass
    
    @abstractmethod
    async def create_session(self, agent_id: str, environment_id: str) -> str:
        """Create a session and return session_id."""
        pass
    
    @abstractmethod
    async def send_message(self, session_id: str, prompt: str) -> None:
        """Send a message to the session."""
        pass
    
    @abstractmethod
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from the session."""
        pass
    
    @abstractmethod
    async def collect_response(self, session_id: str) -> str:
        """Collect the complete response from the session."""
        pass


class AnthropicManagedProvider(ManagedBackendProtocol):
    """
    Anthropic Managed Agents API provider implementation.
    
    Implements the ManagedBackendProtocol for Anthropic's managed agent service.
    Reference: https://platform.claude.com/docs/en/managed-agents/overview
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = None
    
    async def _get_session(self):
        """Get or create aiohttp session."""
        if self.session is None:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "managed-agents-2026-04-01"
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the Anthropic API."""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()
    
    async def create_agent(self, instructions: str, **config) -> str:
        """Create an agent configuration."""
        payload = {
            "instructions": instructions,
            **config
        }
        
        result = await self._request("POST", "/agents", json=payload)
        return result["id"]
    
    async def create_environment(self, **config) -> str:
        """Create a container environment."""
        payload = {
            "type": "container",
            **config
        }
        
        result = await self._request("POST", "/environments", json=payload)
        return result["id"]
    
    async def create_session(self, agent_id: str, environment_id: str) -> str:
        """Create a session."""
        payload = {
            "agent": agent_id,
            "environment_id": environment_id
        }
        
        result = await self._request("POST", "/sessions", json=payload)
        return result["id"]
    
    async def send_message(self, session_id: str, prompt: str) -> None:
        """Send a message to the session."""
        payload = {
            "events": [
                {
                    "type": "user.message",
                    "content": prompt
                }
            ]
        }
        
        await self._request("POST", f"/sessions/{session_id}/events", json=payload)
    
    async def stream_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from the session using SSE."""
        session = await self._get_session()
        url = f"{self.base_url}/sessions/{session_id}/stream"
        
        async with session.get(url) as response:
            response.raise_for_status()
            
            while True:
                line_bytes = await response.content.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode('utf-8').strip()
                if line.startswith('data: '):
                    try:
                        event_data = json.loads(line[6:])  # Remove 'data: ' prefix
                        yield event_data
                    except json.JSONDecodeError:
                        continue
    
    async def collect_response(self, session_id: str) -> str:
        """Collect the complete response from the session."""
        response_parts = []
        
        async for event in self.stream_events(session_id):
            if event.get("type") == "agent.message":
                content = event.get("content", {})
                if isinstance(content, str):
                    response_parts.append(content)
                elif isinstance(content, dict) and "text" in content:
                    response_parts.append(content["text"])
            elif event.get("type") == "session.complete":
                break
        
        return "".join(response_parts)
    
    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None


class ManagedAgentIntegration(BaseCLIIntegration):
    """
    Generic integration for managed agent APIs.
    
    Extends BaseCLIIntegration to provide a consistent interface for external
    managed agent infrastructures. Supports multiple providers through the
    ManagedBackendProtocol.
    
    Attributes:
        provider: Provider name ("anthropic", etc.)
        api_key: API key for the provider
        config: Provider-specific configuration
        backend: The managed backend provider instance
        agent_id: Created agent ID (cached)
        environment_id: Created environment ID (cached)
    """
    
    def __init__(
        self,
        provider: str = "anthropic",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        workspace: str = ".",
        timeout: int = 600,  # Managed agents may take longer than CLI tools
        instructions: str = "You are a helpful AI assistant.",
    ):
        """
        Initialize managed agent integration.
        
        Args:
            provider: Provider name ("anthropic", etc.)
            api_key: API key for the provider
            config: Provider-specific configuration
            workspace: Working directory (for compatibility with base class)
            timeout: Timeout in seconds for operations
            instructions: Default instructions for agent creation
        """
        super().__init__(workspace=workspace, timeout=timeout)
        
        self.provider = provider
        self.api_key = api_key
        self.config = config or {}
        self.instructions = instructions
        
        # Initialize provider
        self.backend = self._create_provider(provider, api_key)
        
        # Cached IDs for reuse
        self.agent_id: Optional[str] = None
        self.environment_id: Optional[str] = None
        self._session_cache: Dict[str, str] = {}
    
    @property
    def cli_command(self) -> str:
        """Return the CLI command name for compatibility."""
        return f"managed-{self.provider}"
    
    @property
    def is_available(self) -> bool:
        """Check if the managed agent service is available."""
        # For managed services, we check if we have an API key and aiohttp
        return (
            aiohttp is not None and 
            self.api_key is not None and 
            self.backend is not None
        )
    
    def _create_provider(self, provider: str, api_key: str) -> Optional[ManagedBackendProtocol]:
        """Create a provider instance based on the provider name."""
        if aiohttp is None:
            # Return None so is_available will be False
            return None
        
        if api_key is None:
            # Try to get from environment
            if provider == "anthropic":
                api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
            self.api_key = api_key
        
        if api_key is None:
            return None
        
        # Persist resolved key so is_available reflects correct state
        self.api_key = api_key
        
        if provider == "anthropic":
            return AnthropicManagedProvider(api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def _ensure_agent(self) -> str:
        """Ensure agent exists and return agent_id."""
        if self.agent_id is None:
            self.agent_id = await self.backend.create_agent(
                self.instructions, 
                **self.config
            )
        return self.agent_id
    
    async def _ensure_environment(self) -> str:
        """Ensure environment exists and return environment_id."""
        if self.environment_id is None:
            self.environment_id = await self.backend.create_environment()
        return self.environment_id
    
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute agent in managed infrastructure.
        
        Args:
            prompt: The prompt/query to send to the agent
            **options: Additional options (session_id for reuse, etc.)
            
        Returns:
            str: The agent's response
        """
        if not self.is_available:
            raise RuntimeError(f"Managed agent service ({self.provider}) is not available")
        
        # Get or create session
        session_key = options.get('session_key', 'default')
        session_id = self._session_cache.get(session_key)
        
        if session_id is None:
            agent_id = await self._ensure_agent()
            environment_id = await self._ensure_environment()
            session_id = await self.backend.create_session(agent_id, environment_id)
            self._session_cache[session_key] = session_id
        
        # Send message
        await self.backend.send_message(session_id, prompt)
        
        # Collect response with timeout
        try:
            return await asyncio.wait_for(
                self.backend.collect_response(session_id),
                timeout=self.timeout
            )
        except asyncio.TimeoutError as err:
            raise RuntimeError(f"Managed agent execution timed out after {self.timeout}s") from err
    
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from managed agent.
        
        Args:
            prompt: The prompt/query to send to the agent
            **options: Additional options
            
        Yields:
            dict: Events from the managed agent
        """
        if not self.is_available:
            raise RuntimeError(f"Managed agent service ({self.provider}) is not available")
        
        # Get or create session
        session_key = options.get('session_key', 'default')
        session_id = self._session_cache.get(session_key)
        
        if session_id is None:
            agent_id = await self._ensure_agent()
            environment_id = await self._ensure_environment()
            session_id = await self.backend.create_session(agent_id, environment_id)
            self._session_cache[session_key] = session_id
        
        # Send message
        await self.backend.send_message(session_id, prompt)
        
        # Stream events with timeout
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.timeout
        
        try:
            async for event in self.backend.stream_events(session_id):
                if loop.time() > deadline:
                    raise asyncio.TimeoutError()
                yield event
        except asyncio.TimeoutError as err:
            raise RuntimeError(f"Managed agent streaming timed out after {self.timeout}s") from err
    
    def reset_session(self, session_key: str = 'default'):
        """Reset a specific session."""
        if session_key in self._session_cache:
            del self._session_cache[session_key]
    
    def reset_all_sessions(self):
        """Reset all sessions."""
        self._session_cache.clear()
    
    async def close(self):
        """Close the managed agent integration and cleanup resources."""
        if hasattr(self.backend, 'close'):
            await self.backend.close()
        self.reset_all_sessions()


# Tool mapping helpers
TOOL_MAPPING = {
    # Managed agent built-in tools -> PraisonAI tool equivalents
    "bash": "execute_command",
    "read": "read_file", 
    "write": "write_file",
    "edit": "apply_diff",
    "glob": "list_files",
    "grep": "search_file", 
    "web_fetch": "web_fetch",
    "search": "search_web",
}


def map_managed_tools(managed_tools: List[str]) -> List[str]:
    """
    Map managed agent tool names to PraisonAI tool names.
    
    Args:
        managed_tools: List of managed agent tool names
        
    Returns:
        List of corresponding PraisonAI tool names
    """
    return [TOOL_MAPPING.get(tool, tool) for tool in managed_tools]