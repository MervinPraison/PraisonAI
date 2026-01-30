"""
AGUI - Main AG-UI Interface Class

Exposes PraisonAI Agents via the AG-UI protocol.
"""

import logging
import uuid
from typing import AsyncIterator, List, Optional, TYPE_CHECKING

from praisonaiagents.ui.agui.types import (
    BaseEvent,
    RunAgentInput,
)
from praisonaiagents.ui.agui.conversion import (
    agui_messages_to_praisonai,
    validate_state,
    extract_user_input,
)
from praisonaiagents.ui.agui.streaming import (
    create_run_error_event,
    async_stream_agent_response,
    async_stream_agents_response,
)
from praisonaiagents.ui.agui.encoder import EventEncoder

if TYPE_CHECKING:
    from praisonaiagents import Agent, AgentManager
    from fastapi import APIRouter

logger = logging.getLogger(__name__)


class AGUI:
    """
    AG-UI Interface for PraisonAI Agents.
    
    Exposes a PraisonAI Agent or Agents workflow via the AG-UI protocol,
    enabling integration with CopilotKit and other AG-UI compatible frontends.
    
    Usage:
        from praisonaiagents import Agent
        from praisonaiagents.ui.agui import AGUI
        from fastapi import FastAPI
        
        agent = Agent(name="Assistant", role="Helper", goal="Help users")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
    
    Args:
        agent: Single PraisonAI Agent instance
        agents: Agents instance for multi-agent workflows
        name: Name for the AG-UI endpoint (defaults to agent name)
        description: Description of the agent
        prefix: URL prefix for the router (e.g., "/api/v1")
        tags: OpenAPI tags for the router
    """
    
    def __init__(
        self,
        agent: Optional["Agent"] = None,
        agents: Optional["Agents"] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        prefix: str = "",
        tags: Optional[List[str]] = None,
    ):
        if agent is None and agents is None:
            raise ValueError("AGUI requires an agent or agents instance")
        
        self.agent = agent
        self.agents = agents
        self.prefix = prefix
        self.tags = tags or ["AGUI"]
        
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
            self.description = "PraisonAI Agent via AG-UI"
        
        self._router: Optional["APIRouter"] = None
    
    def get_router(self) -> "APIRouter":
        """
        Get the FastAPI router for this AGUI instance.
        
        Returns:
            FastAPI APIRouter with AG-UI endpoints
        """
        from fastapi import APIRouter
        from fastapi.responses import StreamingResponse
        
        if self._router is not None:
            return self._router
        
        self._router = APIRouter(prefix=self.prefix, tags=self.tags)
        
        # Attach routes
        self._attach_routes(self._router)
        
        return self._router
    
    def _attach_routes(self, router: "APIRouter") -> None:
        """Attach AG-UI routes to the router."""
        from fastapi.responses import StreamingResponse
        
        encoder = EventEncoder()
        
        @router.post("/agui")
        async def run_agent_agui(run_input: RunAgentInput):
            """Run the agent via AG-UI protocol."""
            async def event_generator():
                async for event in self._run_agent(run_input):
                    yield encoder.encode(event)
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                },
            )
        
        @router.get("/status")
        async def get_status():
            """Get agent status."""
            return {"status": "available"}
    
    async def _run_agent(self, run_input: RunAgentInput) -> AsyncIterator[BaseEvent]:
        """
        Run the agent with the given input.
        
        Args:
            run_input: AG-UI run input
            
        Yields:
            AG-UI events
        """
        run_id = run_input.run_id or str(uuid.uuid4())
        thread_id = run_input.thread_id
        
        try:
            # Convert messages
            messages = run_input.messages or []
            
            # Extract user input
            user_input = extract_user_input(messages)
            
            # Validate state
            session_state = validate_state(run_input.state, thread_id)
            
            # Get user_id from forwarded_props if available
            user_id = None
            if run_input.forwarded_props and isinstance(run_input.forwarded_props, dict):
                user_id = run_input.forwarded_props.get("user_id")
            
            # Run appropriate handler
            if self.agent:
                async for event in async_stream_agent_response(
                    agent=self.agent,
                    user_input=user_input,
                    thread_id=thread_id,
                    run_id=run_id,
                    session_state=session_state,
                    messages=agui_messages_to_praisonai(messages),
                ):
                    yield event
            
            elif self.agents:
                async for event in async_stream_agents_response(
                    agents=self.agents,
                    user_input=user_input,
                    thread_id=thread_id,
                    run_id=run_id,
                    session_state=session_state,
                ):
                    yield event
            
            else:
                yield create_run_error_event("No agent or agents configured")
        
        except Exception as e:
            logger.error(f"Error running agent: {e}", exc_info=True)
            yield create_run_error_event(str(e))
