"""
A2A - Main A2A Interface Class

Exposes PraisonAI Agents via the A2A (Agent2Agent) protocol.
"""

import logging
from typing import List, Optional, TYPE_CHECKING

from praisonaiagents.ui.a2a.types import AgentCard
from praisonaiagents.ui.a2a.agent_card import generate_agent_card
from praisonaiagents.ui.a2a.task_store import TaskStore

if TYPE_CHECKING:
    from praisonaiagents import Agent, AgentManager
    from fastapi import APIRouter

logger = logging.getLogger(__name__)


class A2A:
    """
    A2A Interface for PraisonAI Agents.
    
    Exposes a PraisonAI Agent or Agents workflow via the A2A protocol,
    enabling agent-to-agent communication with other A2A-compatible systems.
    
    Usage:
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        from fastapi import FastAPI
        
        agent = Agent(name="Assistant", role="Helper", goal="Help users")
        a2a = A2A(agent=agent, url="http://localhost:8000/a2a")
        
        app = FastAPI()
        app.include_router(a2a.get_router())
        
        # Agent Card at: GET /.well-known/agent.json
        # A2A endpoint at: POST /a2a
    
    Args:
        agent: Single PraisonAI Agent instance
        agents: Agents instance for multi-agent workflows
        name: Name for the A2A endpoint (defaults to agent name)
        description: Description of the agent
        url: URL where the A2A endpoint is hosted
        version: Version string for the agent
        prefix: URL prefix for the router
        tags: OpenAPI tags for the router
    """
    
    def __init__(
        self,
        agent: Optional["Agent"] = None,
        agents: Optional["Agents"] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        url: str = "http://localhost:8000/a2a",
        version: str = "1.0.0",
        prefix: str = "",
        tags: Optional[List[str]] = None,
    ):
        if agent is None and agents is None:
            raise ValueError("A2A requires an agent or agents instance")
        
        self.agent = agent
        self.agents = agents
        self.url = url
        self.version = version
        self.prefix = prefix
        self.tags = tags or ["A2A"]
        
        # Set name from agent if not provided
        if name:
            self.name = name
        elif agent and hasattr(agent, 'name'):
            self.name = agent.name
        elif agents and hasattr(agents, 'name'):
            self.name = agents.name
        else:
            self.name = "PraisonAI Agent"
        
        # Set description
        if description:
            self.description = description
        elif agent and hasattr(agent, 'role'):
            self.description = agent.role
        else:
            self.description = "PraisonAI Agent via A2A"
        
        # Initialize task store
        self.task_store = TaskStore()
        
        # Router cache
        self._router: Optional["APIRouter"] = None
        self._agent_card: Optional[AgentCard] = None
    
    def get_agent_card(self) -> AgentCard:
        """
        Get the Agent Card for this A2A instance.
        
        Returns:
            AgentCard object for A2A discovery
        """
        if self._agent_card is None:
            self._agent_card = generate_agent_card(
                agent=self.agent,
                url=self.url,
                version=self.version,
                streaming=True,
            )
        return self._agent_card
    
    def get_router(self) -> "APIRouter":
        """
        Get the FastAPI router for this A2A instance.
        
        Returns:
            FastAPI APIRouter with A2A endpoints
        """
        if self._router is None:
            self._router = self._create_router()
        return self._router
    
    def _create_router(self) -> "APIRouter":
        """Create FastAPI router with A2A endpoints."""
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
        
        router = APIRouter(prefix=self.prefix, tags=self.tags)
        
        # Agent Card endpoint (well-known URI)
        @router.get("/.well-known/agent.json")
        async def get_agent_card():
            """Return the Agent Card for discovery."""
            card = self.get_agent_card()
            return JSONResponse(content=card.model_dump(by_alias=True, exclude_none=True))
        
        # Status endpoint
        @router.get("/status")
        async def get_status():
            """Return server status."""
            return {
                "status": "ok",
                "name": self.name,
                "version": self.version,
            }
        
        # TODO: Add JSON-RPC endpoint for message/send
        # TODO: Add streaming endpoint for message/stream
        # TODO: Add task management endpoints
        
        return router
