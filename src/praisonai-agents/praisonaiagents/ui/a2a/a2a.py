"""
A2A - Main A2A Interface Class

Exposes PraisonAI Agents via the A2A (Agent2Agent) protocol.
"""

import asyncio
import logging
from typing import List, Optional, TYPE_CHECKING

from praisonaiagents.ui.a2a.types import AgentCard
from praisonaiagents.ui.a2a.agent_card import generate_agent_card
from praisonaiagents.ui.a2a.task_store import TaskStore

if TYPE_CHECKING:
    from praisonaiagents import Agent, AgentTeam
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
        from fastapi import APIRouter, Request
        from fastapi.responses import JSONResponse, StreamingResponse
        
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
        
        # JSON-RPC 2.0 endpoint for A2A protocol
        @router.post("/a2a")
        async def handle_jsonrpc(request: Request):
            """
            Handle A2A JSON-RPC 2.0 requests.
            
            Supported methods:
            - message/send: Send a message and get a response
            - message/stream: Send a message and stream the response
            - tasks/get: Get task status and history
            - tasks/cancel: Cancel a running task
            """
            try:
                body = await request.json()
            except Exception:
                return _jsonrpc_error(None, -32700, "Parse error: invalid JSON")
            
            # Validate JSON-RPC format
            if body.get("jsonrpc") != "2.0":
                return _jsonrpc_error(
                    body.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'"
                )
            
            request_id = body.get("id")
            method = body.get("method")
            params = body.get("params", {})
            
            # Route to handler
            if method == "message/send":
                return await self._handle_message_send(request_id, params)
            elif method == "message/stream":
                return await self._handle_message_stream(request_id, params)
            elif method == "tasks/get":
                return self._handle_tasks_get(request_id, params)
            elif method == "tasks/cancel":
                return self._handle_tasks_cancel(request_id, params)
            else:
                return _jsonrpc_error(
                    request_id, -32601, f"Method not found: {method}"
                )
        
        return router
    
    async def _handle_message_send(self, request_id, params: dict):
        """Handle message/send — create task, run agent, return result."""
        from fastapi.responses import JSONResponse
        from praisonaiagents.ui.a2a.types import (
            Message, TextPart, TaskState,
        )
        from praisonaiagents.ui.a2a.conversion import (
            extract_user_input,
            praisonai_to_a2a_message,
            create_artifact,
        )
        
        # Validate params
        msg_data = params.get("message")
        if not msg_data:
            return _jsonrpc_error(request_id, -32602, "Invalid params: 'message' required")
        
        # Parse the incoming message
        try:
            message = _parse_message(msg_data)
        except Exception as e:
            return _jsonrpc_error(request_id, -32602, f"Invalid params: {e}")
        
        # Create task in store
        task = self.task_store.create_task(message)
        
        # Update to working
        self.task_store.update_status(task.id, TaskState.WORKING)
        
        try:
            # Extract user input text
            user_input = extract_user_input([message])
            
            # Run agent (offload sync call to thread pool)
            response = await asyncio.to_thread(self.agent.chat, user_input)
            
            # Create response message and artifact
            response_msg = praisonai_to_a2a_message(
                str(response), task_id=task.id
            )
            artifact = create_artifact(str(response))
            
            # Update task store
            self.task_store.add_to_history(task.id, response_msg)
            self.task_store.add_artifact(task.id, artifact)
            updated_task = self.task_store.update_status(task.id, TaskState.COMPLETED)
            
        except Exception as e:
            logger.error(f"Agent error in message/send: {e}")
            updated_task = self.task_store.update_status(task.id, TaskState.FAILED)
        
        # Return JSON-RPC response
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": updated_task.model_dump(by_alias=True, exclude_none=True),
        })
    
    async def _handle_message_stream(self, request_id, params: dict):
        """Handle message/stream — create task, stream agent response as SSE."""
        from fastapi.responses import StreamingResponse
        from praisonaiagents.ui.a2a.types import TaskState
        from praisonaiagents.ui.a2a.streaming import stream_agent_response
        from praisonaiagents.ui.a2a.conversion import extract_user_input
        
        # Validate params
        msg_data = params.get("message")
        if not msg_data:
            return _jsonrpc_error(request_id, -32602, "Invalid params: 'message' required")
        
        # Parse the incoming message
        try:
            message = _parse_message(msg_data)
        except Exception as e:
            return _jsonrpc_error(request_id, -32602, f"Invalid params: {e}")
        
        # Create task in store
        task = self.task_store.create_task(message)
        
        # Extract user input
        user_input = extract_user_input([message])
        
        # Stream the response using existing streaming helper
        return StreamingResponse(
            stream_agent_response(
                agent=self.agent,
                user_input=user_input,
                task_id=task.id,
                context_id=task.context_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    def _handle_tasks_get(self, request_id, params: dict):
        """Handle tasks/get — return existing task."""
        from fastapi.responses import JSONResponse
        
        task_id = params.get("id")
        if not task_id:
            return _jsonrpc_error(request_id, -32602, "Invalid params: 'id' required")
        
        task = self.task_store.get_task(task_id)
        if not task:
            return _jsonrpc_error(request_id, -32000, f"Task not found: {task_id}")
        
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": task.model_dump(by_alias=True, exclude_none=True),
        })
    
    def _handle_tasks_cancel(self, request_id, params: dict):
        """Handle tasks/cancel — cancel existing task."""
        from fastapi.responses import JSONResponse
        
        task_id = params.get("id")
        if not task_id:
            return _jsonrpc_error(request_id, -32602, "Invalid params: 'id' required")
        
        task = self.task_store.cancel_task(task_id)
        if not task:
            return _jsonrpc_error(request_id, -32000, f"Task not found: {task_id}")
        
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": task.model_dump(by_alias=True, exclude_none=True),
        })


# =============================================================================
# Helpers (module-level, no class dependency)
# =============================================================================

def _jsonrpc_error(request_id, code: int, message: str):
    """Create a JSON-RPC 2.0 error response."""
    from fastapi.responses import JSONResponse
    
    return JSONResponse(content={
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    })


def _parse_message(msg_data: dict):
    """Parse a raw dict into an A2A Message object."""
    from praisonaiagents.ui.a2a.types import Message, TextPart, Role
    
    # Handle parts — each part may have 'text' for TextPart
    parts = []
    for part_data in msg_data.get("parts", []):
        if "text" in part_data:
            parts.append(TextPart(text=part_data["text"]))
    
    if not parts:
        raise ValueError("Message must contain at least one part with 'text'")
    
    return Message(
        message_id=msg_data.get("messageId", f"msg-auto"),
        role=msg_data.get("role", "user"),
        parts=parts,
        context_id=msg_data.get("contextId"),
        task_id=msg_data.get("taskId"),
    )
