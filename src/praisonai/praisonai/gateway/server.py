"""
WebSocket Gateway Server for PraisonAI.

Provides a WebSocket-based gateway for multi-agent coordination,
session management, and real-time communication.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.gateway import (
    GatewayConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
)

logger = logging.getLogger(__name__)


@dataclass
class GatewaySession:
    """A gateway session tracking a conversation between client and agent."""
    
    _session_id: str
    _agent_id: str
    _client_id: Optional[str] = None
    _is_active: bool = True
    _created_at: float = field(default_factory=time.time)
    _last_activity: float = field(default_factory=time.time)
    _state: Dict[str, Any] = field(default_factory=dict)
    _messages: List[GatewayMessage] = field(default_factory=list)
    _max_messages: int = 1000
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def agent_id(self) -> Optional[str]:
        return self._agent_id
    
    @property
    def client_id(self) -> Optional[str]:
        return self._client_id
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @property
    def created_at(self) -> float:
        return self._created_at
    
    @property
    def last_activity(self) -> float:
        return self._last_activity
    
    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)
    
    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._last_activity = time.time()
    
    def add_message(self, message: GatewayMessage) -> None:
        self._messages.append(message)
        self._last_activity = time.time()
        if self._max_messages > 0 and len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]
    
    def get_messages(self, limit: Optional[int] = None) -> List[GatewayMessage]:
        if limit:
            return list(self._messages[-limit:])
        return list(self._messages)
    
    def close(self) -> None:
        self._is_active = False


class WebSocketGateway:
    """WebSocket gateway server for multi-agent coordination.
    
    Implements the GatewayProtocol for WebSocket-based communication.
    
    Example:
        from praisonai.gateway import WebSocketGateway
        from praisonaiagents import Agent
        
        # Create gateway
        gateway = WebSocketGateway(port=8765)
        
        # Register agents
        agent = Agent(name="assistant")
        gateway.register_agent(agent)
        
        # Start gateway
        await gateway.start()
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        config: Optional[GatewayConfig] = None,
    ):
        """Initialize the gateway.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            config: Optional gateway configuration
        """
        self.config = config or GatewayConfig(host=host, port=port)
        self._host = self.config.host
        self._port = self.config.port
        
        self._is_running = False
        self._started_at: Optional[float] = None
        self._server = None
        
        self._agents: Dict[str, "Agent"] = {}
        self._sessions: Dict[str, GatewaySession] = {}
        self._clients: Dict[str, Any] = {}  # WebSocket connections
        self._client_sessions: Dict[str, str] = {}  # client_id -> session_id
        
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def port(self) -> int:
        return self._port
    
    @property
    def host(self) -> str:
        return self._host
    
    async def start(self) -> None:
        """Start the gateway server."""
        if self._is_running:
            logger.warning("Gateway already running")
            return
        
        try:
            from starlette.applications import Starlette
            from starlette.routing import Route, WebSocketRoute
            from starlette.responses import JSONResponse
            from starlette.websockets import WebSocket, WebSocketDisconnect
            import uvicorn
        except ImportError:
            raise ImportError(
                "Gateway requires starlette and uvicorn. "
                "Install with: pip install praisonai[api]"
            )
        
        async def health(request):
            return JSONResponse(self.health())
        
        async def info(request):
            return JSONResponse({
                "name": "PraisonAI Gateway",
                "version": "1.0.0",
                "agents": list(self._agents.keys()),
                "sessions": len(self._sessions),
                "clients": len(self._clients),
            })
        
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            client_id = str(uuid.uuid4())
            self._clients[client_id] = websocket
            
            logger.info(f"Client connected: {client_id}")
            
            await self.emit(GatewayEvent(
                type=EventType.CONNECT,
                data={"client_id": client_id},
                source=client_id,
            ))
            
            try:
                while True:
                    data = await websocket.receive_json()
                    await self._handle_client_message(client_id, data)
            except WebSocketDisconnect:
                logger.info(f"Client disconnected: {client_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._clients.pop(client_id, None)
                session_id = self._client_sessions.pop(client_id, None)
                if session_id:
                    self.close_session(session_id)
                
                await self.emit(GatewayEvent(
                    type=EventType.DISCONNECT,
                    data={"client_id": client_id},
                    source=client_id,
                ))
        
        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            WebSocketRoute("/ws", websocket_endpoint),
        ]
        
        app = Starlette(routes=routes)
        
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        
        self._is_running = True
        self._started_at = time.time()
        
        logger.info(f"Gateway started on ws://{self._host}:{self._port}")
        
        await self._server.serve()
    
    async def stop(self) -> None:
        """Stop the gateway server."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.close()
            except Exception:
                pass
        
        self._clients.clear()
        self._client_sessions.clear()
        
        for session in list(self._sessions.values()):
            session.close()
        
        if self._server:
            self._server.should_exit = True
        
        logger.info("Gateway stopped")
    
    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]) -> None:
        """Handle a message from a client."""
        msg_type = data.get("type", "message")
        
        if msg_type == "join":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agents:
                session = self.create_session(agent_id, client_id)
                self._client_sessions[client_id] = session.session_id
                await self._send_to_client(client_id, {
                    "type": "joined",
                    "session_id": session.session_id,
                    "agent_id": agent_id,
                })
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": f"Agent not found: {agent_id}",
                })
        
        elif msg_type == "message":
            session_id = self._client_sessions.get(client_id)
            if session_id:
                session = self._sessions.get(session_id)
                if session:
                    content = data.get("content", "")
                    message = GatewayMessage(
                        content=content,
                        sender_id=client_id,
                        session_id=session_id,
                    )
                    session.add_message(message)
                    
                    response = await self._process_agent_message(session, message)
                    
                    await self._send_to_client(client_id, {
                        "type": "response",
                        "content": response,
                        "session_id": session_id,
                    })
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": "Not joined to any session",
                })
        
        elif msg_type == "leave":
            session_id = self._client_sessions.pop(client_id, None)
            if session_id:
                self.close_session(session_id)
                await self._send_to_client(client_id, {
                    "type": "left",
                    "session_id": session_id,
                })
    
    async def _process_agent_message(
        self,
        session: GatewaySession,
        message: GatewayMessage,
    ) -> str:
        """Process a message through the agent."""
        agent = self._agents.get(session.agent_id)
        if not agent:
            return "Agent not available"
        
        try:
            response = agent.chat(message.content if isinstance(message.content, str) else str(message.content))
            
            response_message = GatewayMessage(
                content=response,
                sender_id=session.agent_id,
                session_id=session.session_id,
                reply_to=message.message_id,
            )
            session.add_message(response_message)
            
            return response
        except Exception as e:
            logger.error(f"Agent error: {e}")
            return f"Error: {str(e)}"
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to a specific client."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
    
    def register_agent(self, agent: "Agent", agent_id: Optional[str] = None) -> str:
        """Register an agent with the gateway."""
        aid = agent_id or getattr(agent, "agent_id", None) or str(uuid.uuid4())
        self._agents[aid] = agent
        logger.info(f"Agent registered: {aid}")
        return aid
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the gateway."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")
            return True
        return False
    
    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """Get a registered agent by ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._agents.keys())
    
    def create_session(
        self,
        agent_id: str,
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewaySession:
        """Create a new session."""
        sid = session_id or str(uuid.uuid4())
        session = GatewaySession(
            _session_id=sid,
            _agent_id=agent_id,
            _client_id=client_id,
            _max_messages=self.config.session_config.max_messages,
        )
        self._sessions[sid] = session
        logger.info(f"Session created: {sid} for agent {agent_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[GatewaySession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info(f"Session closed: {session_id}")
            return True
        return False
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        if agent_id:
            return [
                sid for sid, session in self._sessions.items()
                if session.agent_id == agent_id
            ]
        return list(self._sessions.keys())
    
    def on_event(self, event_type: str) -> Callable:
        """Decorator to register an event handler."""
        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func
        return decorator
    
    async def emit(self, event: GatewayEvent) -> None:
        """Emit an event to registered handlers."""
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
    
    async def broadcast(
        self,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Broadcast an event to all connected clients."""
        exclude_set = set(exclude or [])
        data = event.to_dict()
        
        for client_id, ws in list(self._clients.items()):
            if client_id not in exclude_set:
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.error(f"Broadcast error to {client_id}: {e}")
    
    def health(self) -> Dict[str, Any]:
        """Get gateway health status."""
        uptime = time.time() - self._started_at if self._started_at else 0
        return {
            "status": "healthy" if self._is_running else "stopped",
            "uptime": uptime,
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "clients": len(self._clients),
        }
