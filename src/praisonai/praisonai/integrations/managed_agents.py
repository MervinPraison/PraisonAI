"""
External Managed Agent Backends Integration.

Provides integration with external managed agent infrastructures as execution backends,
starting with Anthropic's Managed Agents API. Uses the official Anthropic Python SDK
(v0.94+) which handles beta headers, auth, and SSE streaming natively.

Usage:
    from praisonai.integrations import ManagedAgentIntegration
    
    # Create managed backend (auto-reads ANTHROPIC_API_KEY)
    managed = ManagedAgentIntegration(
        provider="anthropic",
        config={"model": "claude-sonnet-4-6"}
    )
    
    # Use with PraisonAI Agent
    from praisonaiagents import Agent
    agent = Agent(name="coder", backend=managed)
    result = agent.start("Create a Python script that prints hello")
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ManagedAgentIntegration:
    """
    Generic integration for managed agent APIs.
    
    Uses the official Anthropic Python SDK for the Managed Agents beta API.
    The SDK handles beta headers, authentication, and SSE streaming natively.
    
    Attributes:
        provider: Provider name ("anthropic")
        config: Provider-specific configuration (model, tools, packages, etc.)
        agent_id: Created agent ID (cached for reuse)
        environment_id: Created environment ID (cached for reuse)
    """
    
    def __init__(
        self,
        provider: str = "anthropic",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        timeout: int = 600,
        instructions: str = "You are a helpful AI assistant.",
    ):
        self.provider = provider
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.config = config or {}
        self.timeout = timeout
        self.instructions = instructions
        
        # Cached IDs for reuse across calls
        self.agent_id: Optional[str] = None
        self.environment_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._client = None
    
    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic SDK required for managed agents. "
                    "Install with: pip install 'anthropic>=0.94.0'"
                )
            if not self.api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. "
                    "Export it or pass api_key= to ManagedAgentIntegration."
                )
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client
    
    def _ensure_agent(self) -> str:
        """Create agent if not cached, return agent_id."""
        if self.agent_id:
            return self.agent_id
        
        client = self._get_client()
        model = self.config.get("model", "claude-sonnet-4-6")
        tools = self.config.get("tools", [{"type": "agent_toolset_20260401"}])
        system = self.config.get("system", self.instructions)
        name = self.config.get("name", "PraisonAI Managed Agent")
        
        agent = client.beta.agents.create(
            name=name,
            model=model,
            system=system,
            tools=tools,
        )
        self.agent_id = agent.id
        logger.info(f"Created managed agent: {agent.id} (v{agent.version})")
        return self.agent_id
    
    def _ensure_environment(self) -> str:
        """Create environment if not cached, return environment_id."""
        if self.environment_id:
            return self.environment_id
        
        client = self._get_client()
        env_name = self.config.get("env_name", "praisonai-env")
        packages = self.config.get("packages")
        networking = self.config.get("networking", {"type": "unrestricted"})
        
        env_config = {"type": "cloud", "networking": networking}
        if packages:
            env_config["packages"] = packages
        
        environment = client.beta.environments.create(
            name=env_name,
            config=env_config,
        )
        self.environment_id = environment.id
        logger.info(f"Created managed environment: {environment.id}")
        return self.environment_id
    
    def _ensure_session(self) -> str:
        """Create session if not cached, return session_id."""
        if self._session_id:
            return self._session_id
        
        client = self._get_client()
        agent_id = self._ensure_agent()
        env_id = self._ensure_environment()
        
        session = client.beta.sessions.create(
            agent=agent_id,
            environment_id=env_id,
            title="PraisonAI session",
        )
        self._session_id = session.id
        logger.info(f"Created managed session: {session.id}")
        return self._session_id
    
    async def execute(self, prompt: str, **kwargs) -> str:
        """
        Execute prompt in managed infrastructure and return the full response.
        
        This is the method called by Agent._delegate_to_backend().
        Uses the SDK's synchronous streaming API in a thread to stay async-safe.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_sync, prompt)
    
    def _execute_sync(self, prompt: str) -> str:
        """Synchronous execution using the SDK's native streaming."""
        client = self._get_client()
        session_id = self._ensure_session()
        
        response_parts = []
        tool_log = []
        
        with client.beta.sessions.events.stream(session_id) as stream:
            # Send the user message after opening the stream
            client.beta.sessions.events.send(
                session_id,
                events=[{
                    "type": "user.message",
                    "content": [{"type": "text", "text": prompt}],
                }],
            )
            
            # Process events
            for event in stream:
                etype = getattr(event, "type", None)
                
                if etype == "agent.message":
                    for block in getattr(event, "content", []):
                        text = getattr(block, "text", None)
                        if text:
                            response_parts.append(text)
                
                elif etype == "agent.tool_use":
                    name = getattr(event, "name", "unknown")
                    tool_log.append(name)
                    logger.debug(f"[managed] tool_use: {name}")
                
                elif etype == "session.status_idle":
                    logger.debug("[managed] session idle — done")
                    break
        
        if tool_log:
            logger.info(f"[managed] tools used: {tool_log}")
        
        return "".join(response_parts)
    
    def reset_session(self):
        """Reset session so next execute creates a fresh one."""
        self._session_id = None
    
    def reset_all(self):
        """Reset all cached IDs (agent, environment, session)."""
        self.agent_id = None
        self.environment_id = None
        self._session_id = None
        self._client = None


# Tool mapping helpers
TOOL_MAPPING = {
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