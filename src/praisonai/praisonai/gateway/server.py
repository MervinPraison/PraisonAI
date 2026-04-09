"""
WebSocket Gateway Server for PraisonAI.

Provides a WebSocket-based gateway for multi-agent coordination,
session management, and real-time communication.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
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
    
    # Stepper & Concurrency logic
    _inbox: asyncio.Queue = field(default_factory=asyncio.Queue)
    _is_executing: bool = False
    
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

    async def queue_message(self, message: str) -> None:
        """Queue a user message for execution after the current operation."""
        await self._inbox.put(message)
        
    def get_next_message(self) -> Optional[str]:
        """Fetch the next queued message if available without blocking."""
        if self._inbox.empty():
            return None
        return self._inbox.get_nowait()
        
    def mark_executing(self, status: bool) -> None:
        """Mark the session as currently executing an agent workflow."""
        self._is_executing = status


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
    
    @classmethod
    def from_config_file(
        cls,
        config_path: str = "config.yaml",
        section: str = "gateway",
    ) -> "WebSocketGateway":
        """Create a gateway from a YAML configuration file.
        
        Gap S5: Enables gateway config persistence via standard config files.
        
        Args:
            config_path: Path to the YAML config file
            section: Config section containing gateway settings (default: "gateway")
            
        Returns:
            Configured WebSocketGateway instance
            
        Example config.yaml:
            gateway:
              host: "0.0.0.0"
              port: 8765
              auth_token: "${GATEWAY_AUTH_TOKEN}"
              max_connections: 1000
              heartbeat_interval: 30
        """
        import yaml
        
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()
        
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}
        
        gateway_config = raw.get(section, {})
        if not gateway_config:
            logger.warning(f"No '{section}' section in {config_path}, using defaults")
            return cls()
        
        # Substitute environment variables
        def _substitute(value):
            if isinstance(value, str):
                return cls._substitute_env_vars(value)
            return value
        
        # Build GatewayConfig
        config = GatewayConfig(
            host=_substitute(gateway_config.get("host", "127.0.0.1")),
            port=int(gateway_config.get("port", 8765)),
            auth_token=_substitute(gateway_config.get("auth_token")),
            max_connections=int(gateway_config.get("max_connections", 1000)),
            heartbeat_interval=int(gateway_config.get("heartbeat_interval", 30)),
            reconnect_timeout=int(gateway_config.get("reconnect_timeout", 60)),
            ssl_cert=_substitute(gateway_config.get("ssl_cert")),
            ssl_key=_substitute(gateway_config.get("ssl_key")),
        )
        
        logger.info(f"Gateway config loaded from {config_path}")
        return cls(config=config)
    
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
        
        # Multi-bot lifecycle
        self._channel_bots: Dict[str, Any] = {}  # channel_name -> bot instance
        self._routing_rules: Dict[str, Dict[str, str]] = {}  # channel_name -> {context -> agent_id}
        self._channel_tasks: List[asyncio.Task] = []
        
        # Scheduler tick background task
        self._scheduler_task: Optional[asyncio.Task] = None
    
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
        
        def _check_auth(request) -> Optional[JSONResponse]:
            """Validate auth token if configured. Returns error response or None."""
            if not self.config.auth_token:
                return None
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    {"error": "Authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            token = auth_header[7:]
            if not secrets.compare_digest(token, self.config.auth_token):
                return JSONResponse(
                    {"error": "Invalid authentication token"},
                    status_code=403,
                )
            return None
        
        async def info(request):
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            return JSONResponse({
                "name": "PraisonAI Gateway",
                "version": "1.0.0",
                "agents": list(self._agents.keys()),
                "sessions": len(self._sessions),
                "clients": len(self._clients),
            })
        
        async def websocket_endpoint(websocket: WebSocket):
            # Authenticate WebSocket via query param or first message
            if self.config.auth_token:
                ws_token = websocket.query_params.get("token", "")
                if not secrets.compare_digest(ws_token, self.config.auth_token):
                    await websocket.close(code=4003, reason="Authentication required")
                    return
            
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
        
        # ── Approval endpoints ─────────────────────────────────────────
        # Lazy-import approval machinery so it doesn't slow down startup
        # or fail if optional deps are missing.
        from .exec_approval import Resolution, get_exec_approval_manager
        from .rate_limiter import AuthRateLimiter

        _approval_mgr = get_exec_approval_manager()
        _approval_rate = AuthRateLimiter(max_attempts=10, window_seconds=60)

        async def approval_pending(request):
            """GET /api/approval/pending — list pending approval requests."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_pending", client_ip):
                retry = _approval_rate.time_until_allowed("approval_pending", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            return JSONResponse({
                "pending": _approval_mgr.list_pending(),
                "allow_list": _approval_mgr.allowlist.list(),
            })

        async def approval_resolve(request):
            """POST /api/approval/resolve — approve or deny a tool request.

            Body: {"request_id": "...", "approved": true/false,
                   "reason": "...", "allow_always": false}
            """
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_resolve", client_ip):
                retry = _approval_rate.time_until_allowed("approval_resolve", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            request_id = body.get("request_id", "")
            if not request_id:
                return JSONResponse(
                    {"error": "request_id is required"}, status_code=400,
                )

            resolution = Resolution(
                approved=bool(body.get("approved", False)),
                reason=str(body.get("reason", "")),
                allow_always=bool(body.get("allow_always", False)),
            )

            found = _approval_mgr.resolve(request_id, resolution)
            if not found:
                return JSONResponse(
                    {"error": "Request not found or already resolved"},
                    status_code=404,
                )

            return JSONResponse({
                "resolved": True,
                "request_id": request_id,
                "approved": resolution.approved,
            })

        async def approval_allowlist(request):
            """GET/POST/DELETE /api/approval/allow-list

            GET    → list allow-listed tools
            POST   → add a tool: {"tool_name": "..."}
            DELETE → remove a tool: {"tool_name": "..."}
            """
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_allowlist", client_ip):
                retry = _approval_rate.time_until_allowed("approval_allowlist", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            if request.method == "GET":
                return JSONResponse({
                    "allow_list": _approval_mgr.allowlist.list(),
                })

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            tool_name = body.get("tool_name", "")
            if not tool_name:
                return JSONResponse(
                    {"error": "tool_name is required"}, status_code=400,
                )

            if request.method == "POST":
                _approval_mgr.allowlist.add(tool_name)
                return JSONResponse({"added": tool_name})
            elif request.method == "DELETE":
                removed = _approval_mgr.allowlist.remove(tool_name)
                if not removed:
                    return JSONResponse(
                        {"error": f"'{tool_name}' not in allow-list"},
                        status_code=404,
                    )
                return JSONResponse({"removed": tool_name})

            return JSONResponse({"error": "Method not allowed"}, status_code=405)

        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/api/approval/pending", approval_pending, methods=["GET"]),
            Route("/api/approval/resolve", approval_resolve, methods=["POST"]),
            Route("/api/approval/allow-list", approval_allowlist, methods=["GET", "POST", "DELETE"]),
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
        """Process a message through the agent.
        
        If the agent has a stream_emitter, registers a callback that relays
        token deltas to the connected WebSocket client in real-time via
        TOKEN_STREAM / TOOL_CALL_STREAM / STREAM_END events.
        """
        agent = self._agents.get(session.agent_id)
        if not agent:
            return "Agent not available"
        
        client_id = session.client_id
        content = message.content if isinstance(message.content, str) else str(message.content)
        
        # Inbox & Stepper logic
        if session._is_executing:
            # Send an ephemeral status event
            await self._send_to_client(
                client_id,
                {
                    "type": "status",
                    "source": session.agent_id,
                    "message": "Thinking... (I've added your new message to the queue to process next)."
                }
            )
            await session.queue_message(content)
            return "Message queued."
            
        session.mark_executing(True)
        await session.queue_message(content)
        
        # Start background task to process the queue
        asyncio.create_task(self._run_session_queue(session, agent, client_id))
        return "Started processing."

    async def _run_session_queue(self, session: GatewaySession, agent: Any, client_id: str) -> None:
        """Background task loop that constantly pulls from `_inbox` and executes the agent task."""
        try:
            while True:
                content = session.get_next_message()
                if not content:
                    break  # Queue is empty, exit loop
                
                # Wire streaming relay if agent has a stream_emitter
                relay_callback = None
                emitter = getattr(agent, 'stream_emitter', None)
                if emitter is not None and client_id:
                    relay_callback = self._make_stream_relay(client_id, session)
                    emitter.add_callback(relay_callback)
                
                try:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, agent.chat, content)
                except Exception as e:
                    logger.error(f"Agent error in queue processor: {e}")
                    response = f"Error: {str(e)}"
                finally:
                    # Always clean up the relay callback
                    if relay_callback and emitter is not None:
                        try:
                            emitter.remove_callback(relay_callback)
                        except (ValueError, AttributeError):
                            pass
                
                response_message = GatewayMessage(
                    content=response,
                    sender_id=session.agent_id,
                    session_id=session.session_id,
                )
                session.add_message(response_message)
                
                await self._send_to_client(client_id, {
                    "type": "response",
                    "content": response,
                    "session_id": session.session_id,
                })
        finally:
            session.mark_executing(False)

    def _make_stream_relay(
        self, client_id: str, session: "GatewaySession"
    ) -> Callable:
        """Create a StreamCallback that relays events to a WS client.
        
        The callback is synchronous (called from the LLM streaming thread)
        and uses asyncio.run_coroutine_threadsafe to push events into the
        gateway's event loop for WS delivery.
        """
        gateway = self

        def _relay(event) -> None:
            try:
                from praisonaiagents.streaming.events import StreamEventType
                
                event_type = getattr(event, 'type', None)
                if event_type is None:
                    return
                
                # Map StreamEventType -> gateway EventType
                if event_type == StreamEventType.DELTA_TEXT:
                    gw_type = EventType.TOKEN_STREAM
                    data = {
                        "content": getattr(event, 'content', ''),
                        "session_id": session.session_id,
                    }
                elif event_type == StreamEventType.DELTA_TOOL_CALL:
                    gw_type = EventType.TOOL_CALL_STREAM
                    data = {
                        "tool_call": getattr(event, 'tool_call', {}),
                        "session_id": session.session_id,
                    }
                elif event_type == StreamEventType.STREAM_END:
                    gw_type = EventType.STREAM_END
                    data = {"session_id": session.session_id}
                else:
                    return  # Skip non-essential events
                
                gw_event = GatewayEvent(
                    type=gw_type,
                    data=data,
                    source=session.agent_id,
                    target=client_id,
                )
                
                # Thread-safe async send
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        gateway._send_to_client(client_id, gw_event.to_dict()),
                        loop,
                    )
            except Exception as e:
                logger.debug(f"Stream relay error (non-fatal): {e}")

        return _relay
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to a specific client."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
    
    def register_agent(
        self,
        agent: "Agent",
        agent_id: Optional[str] = None,
        *,
        overwrite: bool = True,
    ) -> str:
        """Register an agent with the gateway.
        
        Args:
            agent: The agent instance to register
            agent_id: Optional custom ID (auto-generated if not provided)
            overwrite: If False, raises ValueError on duplicate ID (default: True for backward compat)
            
        Returns:
            The agent ID used for registration
            
        Raises:
            ValueError: If overwrite=False and agent_id already exists
        """
        aid = agent_id or getattr(agent, "agent_id", None) or str(uuid.uuid4())
        
        # B10: Handle duplicate registration
        if aid in self._agents:
            if not overwrite:
                raise ValueError(
                    f"Agent '{aid}' already registered. Use overwrite=True to replace."
                )
            logger.warning(f"Overwriting existing agent: {aid}")
        
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
    
    # ── Client Management (Public API) ────────────────────────────────
    
    def add_client(self, client_id: str, websocket: Any) -> None:
        """Register a client WebSocket connection.
        
        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection object
        """
        self._clients[client_id] = websocket
        logger.debug(f"Client added: {client_id}")
    
    def remove_client(self, client_id: str) -> bool:
        """Unregister a client connection.
        
        Args:
            client_id: The client ID to remove
            
        Returns:
            True if client was found and removed, False otherwise
        """
        removed = self._clients.pop(client_id, None) is not None
        if removed:
            logger.debug(f"Client removed: {client_id}")
        return removed
    
    def get_client(self, client_id: str) -> Optional[Any]:
        """Get a client WebSocket by ID.
        
        Args:
            client_id: The client ID to look up
            
        Returns:
            The WebSocket connection or None if not found
        """
        return self._clients.get(client_id)
    
    def list_clients(self) -> List[str]:
        """List all connected client IDs.
        
        Returns:
            List of client IDs
        """
        return list(self._clients.keys())
    
    # ── Channel Bot Management (Public API - B7) ─────────────────────────
    
    def list_channel_bots(self) -> List[str]:
        """List all registered channel bot names.
        
        Returns:
            List of channel bot names (e.g., ['discord', 'telegram'])
        """
        return list(self._channel_bots.keys())
    
    def get_channel_bot(self, name: str) -> Optional[Any]:
        """Get a channel bot by name.
        
        Args:
            name: The channel bot name (e.g., 'discord', 'telegram')
            
        Returns:
            The bot instance or None if not found
        """
        return self._channel_bots.get(name)
    
    def has_channel_bot(self, name: str) -> bool:
        """Check if a channel bot is registered.
        
        Args:
            name: The channel bot name
            
        Returns:
            True if the bot exists, False otherwise
        """
        return name in self._channel_bots
    
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
        """Get gateway health status including per-channel bot status."""
        uptime = time.time() - self._started_at if self._started_at else 0
        channel_status = {}
        for name, bot in self._channel_bots.items():
            running = getattr(bot, "is_running", False)
            platform = getattr(bot, "platform", "unknown")
            channel_status[name] = {
                "platform": platform,
                "running": running,
            }
        return {
            "status": "healthy" if self._is_running else "stopped",
            "uptime": uptime,
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "clients": len(self._clients),
            "channels": channel_status,
        }

    # ── Scheduled delivery ────────────────────────────────────────────

    async def _deliver_scheduled_result(
        self, delivery: Any, text: str,
    ) -> None:
        """Route a scheduled job result to the correct channel bot.

        Args:
            delivery: A ``DeliveryTarget`` with ``channel`` and ``channel_id``.
            text: The agent response to deliver.
        """
        channel = getattr(delivery, "channel", "") or ""
        channel_id = getattr(delivery, "channel_id", "") or ""
        thread_id = getattr(delivery, "thread_id", None)

        if not channel or not channel_id:
            logger.warning("Delivery target missing channel or channel_id, skipping")
            return

        bot = self.get_channel_bot(channel)
        if bot is None:
            # Try case-insensitive lookup
            for name, b in self._channel_bots.items():
                if name.lower() == channel.lower():
                    bot = b
                    break

        if bot is None:
            logger.warning(
                "No channel bot '%s' found for scheduled delivery", channel,
            )
            return

        try:
            await bot.send_message(
                channel_id, text, thread_id=thread_id,
            )
            logger.info(
                "Delivered scheduled result to %s:%s", channel, channel_id,
            )
        except Exception as e:
            logger.error(
                "Failed to deliver to %s:%s: %s", channel, channel_id, e,
            )

    def _start_scheduler_tick(self, interval: float = 15.0) -> None:
        """Start a background task that polls the scheduler for due jobs.

        Creates a ``ScheduledAgentExecutor`` wired to:
        - a ``ScheduleRunner`` with a ``FileScheduleStore``
        - this gateway's agent registry for resolution
        - ``_deliver_scheduled_result`` for outbound delivery
        """
        async def _run():
            try:
                from praisonaiagents.scheduler import (
                    ScheduleRunner,
                    FileScheduleStore,
                )
                from praisonai.scheduler.executor import ScheduledAgentExecutor
            except ImportError as e:
                logger.warning(
                    "Scheduler dependencies not available, skipping tick: %s", e,
                )
                return

            store = FileScheduleStore()
            runner = ScheduleRunner(store)

            def _resolve_agent(agent_id):
                if agent_id:
                    return self._agents.get(agent_id)
                # Fallback: first registered agent
                return next(iter(self._agents.values()), None) if self._agents else None

            executor = ScheduledAgentExecutor(
                runner=runner,
                agent_resolver=_resolve_agent,
                delivery_handler=self._deliver_scheduled_result,
            )
            await executor.run_loop(interval=interval)

        self._scheduler_task = asyncio.create_task(_run())
        logger.info("Scheduler tick started (interval=15s)")

    # ── Multi-bot lifecycle ───────────────────────────────────────────

    @staticmethod
    def _substitute_env_vars(value: str) -> str:
        """Replace ${VAR_NAME} patterns with environment variable values."""
        if not isinstance(value, str):
            return value
        def _replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                logger.warning(f"Environment variable {var_name} not set")
                return match.group(0)
            return env_val
        return re.sub(r'\$\{([^}]+)\}', _replacer, value)

    @classmethod
    def load_gateway_config(cls, config_path: str) -> Dict[str, Any]:
        """Load and parse a gateway.yaml configuration file.

        Performs environment variable substitution on all string values.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            Parsed configuration dictionary with env vars resolved.
        """
        import yaml

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Gateway config not found: {config_path}")

        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Invalid gateway config: {config_path}")

        # ── Schema validation ──────────────────────────────────────
        errors = []
        if "agents" not in raw:
            errors.append("Missing required 'agents' section")
        elif not isinstance(raw["agents"], dict) or not raw["agents"]:
            errors.append("'agents' must be a non-empty dictionary")
        else:
            for aid, adef in raw["agents"].items():
                if not isinstance(adef, dict):
                    errors.append(f"Agent '{aid}' must be a dictionary")

        if "channels" not in raw:
            errors.append("Missing required 'channels' section")
        elif not isinstance(raw["channels"], dict) or not raw["channels"]:
            errors.append("'channels' must be a non-empty dictionary")
        else:
            valid_platforms = {"telegram", "discord", "slack", "whatsapp", "email", "agentmail"}
            for cname, cdef in raw["channels"].items():
                if not isinstance(cdef, dict):
                    errors.append(f"Channel '{cname}' must be a dictionary")
                    continue
                # Resolve platform: explicit field takes priority over key
                platform = cdef.get("platform", cname).lower()
                if platform not in valid_platforms:
                    logger.warning(
                        f"Channel '{cname}' platform '{platform}' is not "
                        f"a known platform ({', '.join(sorted(valid_platforms))})"
                    )
                # WhatsApp web mode doesn't require a token
                is_wa_web = (platform == "whatsapp" and
                             cdef.get("mode", "cloud").lower().strip() == "web")
                # Email/AgentMail use env vars for tokens — not required in YAML
                is_email_platform = platform in ("email", "agentmail")
                if not cdef.get("token") and not is_wa_web and not is_email_platform:
                    errors.append(
                        f"Channel '{cname}' missing 'token' "
                        "(use ${{ENV_VAR}} syntax for env vars)"
                    )

        if errors:
            msg = (
                f"Gateway config validation failed ({config_path}):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
            raise ValueError(msg)

        def _resolve(obj):
            if isinstance(obj, str):
                return cls._substitute_env_vars(obj)
            if isinstance(obj, dict):
                return {k: _resolve(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_resolve(v) for v in obj]
            return obj

        return _resolve(raw)

    def _create_agents_from_config(
        self,
        agents_cfg: Dict[str, Dict[str, Any]],
        *,
        default_model: Optional[str] = None,
        guardrails_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create and register Agent instances from the agents section of config.

        Supports all agent configuration options including:
        - tools: List of tool names to resolve via ToolResolver
        - tool_choice: Tool selection mode ('auto', 'required', 'none')
        - reflection: Enable reflection/interactive mode (default: True)
        - allow_delegation: Allow task delegation
        - role: Agent role (CrewAI-style)
        - goal: Agent goal (CrewAI-style)
        - backstory: Agent backstory (CrewAI-style)
        - temperature: LLM temperature (optional, uses SDK default)
        - base_url: Custom LLM endpoint URL (optional)
        - api_key: API key for LLM provider (optional)

        Args:
            agents_cfg: The ``agents`` section of the config.
            default_model: Fallback model when an agent has no ``model`` key
                           (e.g. from the ``provider.model`` section of UI config).
            guardrails_cfg: Optional ``guardrails.registry`` dict to wire per-agent.
        """
        from praisonaiagents import Agent

        # Resolve tool names to callables (same pattern as agents_generator)
        tool_resolver = None
        try:
            from praisonai.tool_resolver import ToolResolver
            tool_resolver = ToolResolver()
        except ImportError:
            logger.debug("ToolResolver not available, agents will have no tools")

        for agent_id, agent_def in agents_cfg.items():
            instructions = agent_def.get("instructions", "")
            # G7: Apply provider.model as fallback when agent has no model
            model = agent_def.get("model", None) or default_model
            memory = agent_def.get("memory", False)

            # G2: Pass temperature through (optional, SDK uses its own default)
            temperature = agent_def.get("temperature", None)
            # G3/G4: Pass base_url and api_key for multi-provider support
            base_url = agent_def.get("base_url", None)
            api_key = agent_def.get("api_key", None)

            # Support role/goal/backstory for CrewAI-style agents
            role = agent_def.get("role", None)
            goal = agent_def.get("goal", None)
            backstory = agent_def.get("backstory", None)

            # G6: Fall back to system_prompt if instructions is empty
            if not instructions:
                instructions = agent_def.get("system_prompt", "") or ""

            # Resolve tools from YAML config
            agent_tools = []
            yaml_tool_names = agent_def.get("tools", [])
            if yaml_tool_names and tool_resolver:
                for tool_name in yaml_tool_names:
                    if not tool_name or not isinstance(tool_name, str):
                        continue
                    tool_name = tool_name.strip()
                    resolved = tool_resolver.resolve(tool_name)
                    if resolved:
                        agent_tools.append(resolved)
                        logger.debug(f"Resolved tool '{tool_name}' for agent '{agent_id}'")
                    else:
                        logger.warning(f"Tool '{tool_name}' not found for agent '{agent_id}'")

            # Additional agent options from YAML
            tool_choice = agent_def.get("tool_choice", None)
            reflection = agent_def.get("reflection", True)
            allow_delegation = agent_def.get("allow_delegation", False)

            # G5: Wire guardrails if config has a matching agent_name or global rule
            guardrail_prompt = None
            if guardrails_cfg:
                for _gr_id, gr_def in guardrails_cfg.items():
                    gr_agent = gr_def.get("agent_name", "")
                    if not gr_agent or gr_agent == agent_id:
                        guardrail_prompt = gr_def.get("description", None)
                        break  # first match wins

            # Compose model as dict when temperature is specified
            # (Agent accepts temperature via dict model config)
            model_cfg = model
            if temperature is not None and model and isinstance(model, str):
                model_cfg = {"model": model, "temperature": temperature}

            # Use model= (preferred) instead of deprecated llm=
            agent = Agent(
                name=agent_id,
                instructions=instructions,
                model=model_cfg,
                memory=memory,
                tools=agent_tools if agent_tools else None,
                reflection=reflection,
                allow_delegation=allow_delegation,
                role=role,
                goal=goal,
                backstory=backstory,
                base_url=base_url,
                api_key=api_key,
                guardrails=guardrail_prompt,
            )

            # Store tool_choice for later use in chat()
            if tool_choice:
                agent._yaml_tool_choice = tool_choice

            self.register_agent(agent, agent_id=agent_id)
            logger.info(
                f"Created agent '{agent_id}' "
                f"(model={model}, tools={len(agent_tools)}, "
                f"reflection={reflection})"
            )

    def _determine_routing_context(
        self, channel_type: str, message_metadata: Dict[str, Any]
    ) -> str:
        """Determine the routing context key for a message.

        Args:
            channel_type: Platform name (telegram, discord, slack).
            message_metadata: Dict with at least 'chat_type' or 'is_dm' keys.

        Returns:
            Context string: 'dm', 'group', 'channel', or 'default'.
        """
        chat_type = message_metadata.get("chat_type", "")
        is_dm = message_metadata.get("is_dm", False)

        if is_dm or chat_type in ("private", "dm"):
            return "dm"
        if chat_type in ("group", "supergroup", "guild"):
            return "group"
        if chat_type == "channel":
            return "channel"
        return "default"

    def _resolve_agent_for_message(
        self, channel_name: str, context: str
    ) -> Optional["Agent"]:
        """Look up the correct agent for a channel + context."""
        rules = self._routing_rules.get(channel_name, {})
        agent_id = rules.get(context) or rules.get("default", "default")
        agent = self._agents.get(agent_id)
        if not agent:
            logger.warning(
                f"No agent '{agent_id}' for channel={channel_name} context={context}"
            )
        return agent

    async def start_channels(self, channels_cfg: Dict[str, Dict[str, Any]]) -> None:
        """Start bot instances for each configured channel.

        Each bot runs as a concurrent asyncio task.  If a single bot fails
        to start the others continue running.

        Args:
            channels_cfg: The ``channels`` section of gateway.yaml.
        """
        from praisonaiagents.bots import BotConfig

        for channel_name, ch_cfg in channels_cfg.items():
            channel_type = ch_cfg.get("platform", channel_name).lower()
            token = ch_cfg.get("token", "")
            # WhatsApp web mode doesn't require a token
            wa_web_mode = (channel_type == "whatsapp" and
                           ch_cfg.get("mode", "cloud").lower().strip() == "web")
            # Email/AgentMail use env vars for tokens — not required in YAML
            is_email_platform = channel_type in ("email", "agentmail")
            if not token and not wa_web_mode and not is_email_platform:
                logger.warning(f"No token for channel '{channel_name}', skipping")
                continue

            routes = ch_cfg.get("routing") or ch_cfg.get("routes") or {"default": "default"}
            self._routing_rules[channel_name] = routes

            # Resolve default agent for this channel (used as the bot's primary agent)
            default_agent_id = routes.get("default", list(self._agents.keys())[0] if self._agents else "default")
            default_agent = self._agents.get(default_agent_id)
            if not default_agent:
                logger.warning(f"Default agent '{default_agent_id}' not found for channel '{channel_name}', skipping")
                continue

            config = BotConfig(token=token)

            try:
                bot = self._create_bot(channel_type, token, default_agent, config, ch_cfg)
                if bot is None:
                    continue
                self._channel_bots[channel_name] = bot
                logger.info(f"Channel '{channel_name}' ({channel_type}) initialized")
            except Exception as e:
                logger.error(f"Failed to create bot for '{channel_name}': {e}")
                continue

        # Start all bots concurrently
        if self._channel_bots:
            for name, bot in self._channel_bots.items():
                task = asyncio.create_task(self._run_bot_safe(name, bot))
                self._channel_tasks.append(task)
            logger.info(f"Started {len(self._channel_bots)} channel bot(s)")

    def _create_bot(
        self,
        channel_type: str,
        token: str,
        agent: "Agent",
        config: Any,
        ch_cfg: Dict[str, Any],
    ) -> Any:
        """Create a bot instance for the given channel type."""
        if channel_type == "telegram":
            from praisonai.bots import TelegramBot
            return TelegramBot(token=token, agent=agent, config=config)
        elif channel_type == "discord":
            from praisonai.bots import DiscordBot
            return DiscordBot(token=token, agent=agent, config=config)
        elif channel_type == "slack":
            from praisonai.bots import SlackBot
            app_token = ch_cfg.get("app_token", os.environ.get("SLACK_APP_TOKEN", ""))
            return SlackBot(token=token, agent=agent, config=config, app_token=app_token)
        elif channel_type == "whatsapp":
            from praisonai.bots import WhatsAppBot
            wa_mode = ch_cfg.get("mode", "cloud").lower().strip()
            return WhatsAppBot(
                token=token,
                phone_number_id=ch_cfg.get("phone_number_id", ""),
                agent=agent,
                config=config,
                verify_token=ch_cfg.get("verify_token", ""),
                webhook_port=int(ch_cfg.get("webhook_port", 8080)),
                mode=wa_mode,
                creds_dir=ch_cfg.get("creds_dir"),
            )
        elif channel_type == "email":
            from praisonai.bots import EmailBot
            email_token = token or os.environ.get("EMAIL_APP_PASSWORD", "")
            return EmailBot(
                token=email_token,
                agent=agent,
                email_address=ch_cfg.get("email_address") or os.environ.get("EMAIL_ADDRESS", ""),
                imap_server=ch_cfg.get("imap_server") or os.environ.get("EMAIL_IMAP_SERVER", ""),
                smtp_server=ch_cfg.get("smtp_server") or os.environ.get("EMAIL_SMTP_SERVER", ""),
            )
        elif channel_type == "agentmail":
            from praisonai.bots import AgentMailBot
            am_token = token or os.environ.get("AGENTMAIL_API_KEY", "")
            return AgentMailBot(
                token=am_token,
                agent=agent,
                inbox_id=ch_cfg.get("inbox_id") or os.environ.get("AGENTMAIL_INBOX_ID", ""),
                domain=ch_cfg.get("domain") or os.environ.get("AGENTMAIL_DOMAIN", ""),
            )
        else:
            logger.warning(f"Unknown channel type: {channel_type}")
            return None

    async def _run_bot_safe(self, name: str, bot: Any) -> None:
        """Run a single bot, catching errors so other bots stay alive.

        For TelegramBot, uses the low-level initialize/start/start_polling
        API to avoid event-loop conflicts with ``run_polling()``.
        For Discord/Slack, injects a routing-aware message handler before
        starting so the gateway's routing rules are respected.
        """
        max_retries = 5
        base_delay = 5  # seconds
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Starting bot for channel '{name}'..." + (f" (retry {attempt})" if attempt else ""))

                # TelegramBot special handling: run_polling() tries to manage
                # its own event loop which conflicts with our gateway loop.
                # Use the lower-level API instead.
                if self._is_telegram_bot(bot):
                    await self._start_telegram_bot_polling(name, bot)
                elif type(bot).__name__ == "WhatsAppBot":
                    # WhatsApp runs its own aiohttp webhook server
                    self._inject_routing_handler(name, bot)
                    await bot.start()
                else:
                    # Inject routing-aware handler for Discord/Slack
                    self._inject_routing_handler(name, bot)
                    await bot.start()
                break  # clean exit
            except asyncio.CancelledError:
                logger.info(f"Bot '{name}' cancelled")
                break
            except Exception as e:
                logger.error(f"Bot '{name}' crashed: {e}")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Reconnecting '{name}' in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Bot '{name}' failed after {max_retries} retries, giving up")

    @staticmethod
    def _is_telegram_bot(bot: Any) -> bool:
        """Check if a bot instance is a TelegramBot."""
        return type(bot).__name__ == "TelegramBot"

    def _inject_routing_handler(self, channel_name: str, bot: Any) -> None:
        """Inject a routing-aware on_message handler into a Discord/Slack bot.

        This overrides the bot's default agent with a dynamically-resolved
        agent based on the gateway's routing rules for each incoming message.
        """
        gateway = self

        @bot.on_message
        async def _routed_message_handler(message):
            if not message.sender:
                return
            # Determine routing context from channel type
            ch_type = message.channel.channel_type if message.channel else ""
            is_dm = ch_type in ("dm", "private")
            routing_ctx = gateway._determine_routing_context(
                channel_name, {"chat_type": ch_type, "is_dm": is_dm}
            )
            agent = gateway._resolve_agent_for_message(channel_name, routing_ctx)
            if agent:
                bot.set_agent(agent)

        logger.info(f"Injected routing handler for channel '{channel_name}'")

    async def _start_telegram_bot_polling(self, name: str, bot: Any) -> None:
        """Start a TelegramBot using low-level PTB API for shared event loop.

        Uses ``initialize() -> start() -> updater.start_polling()`` instead
        of the high-level ``run_polling()`` which owns the event loop.
        """
        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error("python-telegram-bot not installed, cannot start Telegram channel")
            return

        app = Application.builder().token(bot._token).build()

        # Copy handlers from the bot's application if it was already built
        # Otherwise, re-build handlers here using the bot's setup logic
        bot._application = app
        bot._started_at = time.time()

        # Get bot info
        bot_info = await app.bot.get_me()
        from praisonaiagents.bots import BotUser
        bot._bot_user = BotUser(
            user_id=str(bot_info.id),
            username=bot_info.username,
            display_name=bot_info.first_name,
            is_bot=True,
        )

        # Set up message handler with routing support
        channel_name = name
        gateway = self

        async def handle_message(update: Update, context: Any):
            if not update.message:
                return

            message_text = None
            if update.message.voice or update.message.audio:
                message_text = await bot._transcribe_audio(update)
            elif update.message.text:
                message_text = update.message.text

            if not message_text:
                return

            user_id = str(update.message.from_user.id) if update.message.from_user else "unknown"

            # Determine routing context
            chat_type = update.message.chat.type if update.message.chat else "private"
            routing_ctx = gateway._determine_routing_context(
                "telegram", {"chat_type": chat_type}
            )
            agent = gateway._resolve_agent_for_message(channel_name, routing_ctx)
            if not agent:
                agent = bot._agent  # fallback to default

            # Show typing indicator
            if bot.config.typing_indicator:
                await update.message.chat.send_action("typing")

            # Ack reaction — show processing indicator
            ack_ctx = None
            if bot._ack.enabled:
                async def _tg_react(emoji, **kw):
                    try:
                        from telegram import ReactionTypeEmoji
                        await app.bot.set_message_reaction(
                            chat_id=update.message.chat_id,
                            message_id=update.message.message_id,
                            reaction=[ReactionTypeEmoji(emoji=emoji)],
                        )
                    except Exception:
                        pass
                async def _tg_unreact(emoji, **kw):
                    try:
                        await app.bot.set_message_reaction(
                            chat_id=update.message.chat_id,
                            message_id=update.message.message_id,
                            reaction=[],
                        )
                    except Exception:
                        pass
                ack_ctx = await bot._ack.ack(react_fn=_tg_react)

            try:
                message_text = await bot._debouncer.debounce(user_id, message_text)
                response = await bot._session.chat(agent, user_id, message_text)
                if hasattr(bot, '_send_response_with_media'):
                    await bot._send_response_with_media(
                        update.message.chat_id,
                        response,
                        reply_to=update.message.message_id,
                    )
                else:
                    await update.message.reply_text(str(response))
                # Done reaction
                if ack_ctx:
                    await bot._ack.done(ack_ctx, react_fn=_tg_react, unreact_fn=_tg_unreact)
            except Exception as e:
                logger.error(f"Agent error in {name}: {e}")
                await update.message.reply_text(f"Error: {str(e)}")

        async def handle_voice(update: Update, context: Any):
            await handle_message(update, context)

        async def handle_status(update: Update, context: Any):
            if not update.message:
                return
            await update.message.reply_text(bot._format_status())

        async def handle_new(update: Update, context: Any):
            if not update.message:
                return
            user_id = str(update.message.from_user.id) if update.message.from_user else "unknown"
            bot._session.reset(user_id)
            await update.message.reply_text("Session reset. Starting fresh conversation.")

        async def handle_help(update: Update, context: Any):
            if not update.message:
                return
            await update.message.reply_text(bot._format_help())

        # Register handlers
        app.add_handler(CommandHandler("status", handle_status))
        app.add_handler(CommandHandler("new", handle_new))
        app.add_handler(CommandHandler("help", handle_help))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

        # Initialize and start using low-level API
        await app.initialize()
        await app.start()
        await app.updater.start_polling(poll_interval=bot.config.polling_interval)

        bot._is_running = True
        logger.info(f"Telegram bot started: @{bot._bot_user.username}")

        # Keep alive until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"Stopping Telegram bot '{name}'...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            bot._is_running = False

    async def stop_channels(self) -> None:
        """Gracefully stop all running channel bots."""
        for task in self._channel_tasks:
            task.cancel()

        if self._channel_tasks:
            await asyncio.gather(*self._channel_tasks, return_exceptions=True)
            self._channel_tasks.clear()

        for name, bot in list(self._channel_bots.items()):
            try:
                if hasattr(bot, "stop"):
                    await bot.stop()
                logger.info(f"Stopped bot '{name}'")
            except Exception as e:
                logger.error(f"Error stopping bot '{name}': {e}")

        self._channel_bots.clear()
        self._routing_rules.clear()

    async def reload_config(self, config_path: str) -> None:
        """Hot-reload gateway.yaml — restarts channels with updated config.

        Agents are recreated and channels are restarted.  The WebSocket
        server itself is **not** restarted (existing connections kept alive).
        """
        logger.info(f"Hot-reloading gateway config from {config_path}...")
        try:
            cfg = self.load_gateway_config(config_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Reload failed — config invalid: {e}")
            return

        # Stop existing channels
        await self.stop_channels()

        # Recreate agents
        agents_cfg = cfg.get("agents", {})
        provider_cfg = cfg.get("provider", {})
        default_model = provider_cfg.get("model") if provider_cfg else None
        guardrails_cfg = (cfg.get("guardrails") or {}).get("registry")
        if agents_cfg:
            self._agents.clear()
            self._create_agents_from_config(
                agents_cfg,
                default_model=default_model,
                guardrails_cfg=guardrails_cfg,
            )

        # Restart channels
        channels_cfg = cfg.get("channels", {})
        if channels_cfg:
            await self.start_channels(channels_cfg)

        logger.info("Hot-reload complete")

    async def _watch_config(self, config_path: str, poll_interval: float = 5.0) -> None:
        """Poll the config file for changes and trigger hot-reload."""
        last_mtime: float = 0.0
        try:
            last_mtime = os.path.getmtime(config_path)
        except OSError:
            pass

        while True:
            await asyncio.sleep(poll_interval)
            try:
                mtime = os.path.getmtime(config_path)
                if mtime > last_mtime:
                    last_mtime = mtime
                    await self.reload_config(config_path)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Config watch error: {e}")

    async def start_with_config(self, config_path: str) -> None:
        """Start the gateway with a gateway.yaml configuration.

        This loads agents from the config, starts channel bots, then
        starts the WebSocket server.  All run concurrently.

        Args:
            config_path: Path to gateway.yaml.
        """
        cfg = self.load_gateway_config(config_path)

        # Apply gateway section overrides
        gw_cfg = cfg.get("gateway", {})
        if gw_cfg.get("host"):
            self._host = gw_cfg["host"]
        if gw_cfg.get("port"):
            self._port = int(gw_cfg["port"])

        # Create agents
        agents_cfg = cfg.get("agents", {})
        provider_cfg = cfg.get("provider", {})
        default_model = provider_cfg.get("model") if provider_cfg else None
        guardrails_cfg = (cfg.get("guardrails") or {}).get("registry")
        if agents_cfg:
            self._create_agents_from_config(
                agents_cfg,
                default_model=default_model,
                guardrails_cfg=guardrails_cfg,
            )

        # Start channels + WebSocket server concurrently
        channels_cfg = cfg.get("channels", {})

        # Start config file watcher for hot-reload
        self._config_watch_task: Optional[asyncio.Task] = None

        async def _run_all():
            if channels_cfg:
                await self.start_channels(channels_cfg)
            # Launch config watcher in background
            self._config_watch_task = asyncio.create_task(
                self._watch_config(config_path)
            )
            # Launch scheduler tick to poll for due jobs
            self._start_scheduler_tick()
            await self.start()

        # Register signal handlers for graceful shutdown using
        # loop.add_signal_handler (async-safe) with signal.signal fallback.
        import signal

        def _request_shutdown():
            logger.info("Received shutdown signal, stopping gateway...")
            if self._server:
                self._server.should_exit = True

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_shutdown)
            except (NotImplementedError, OSError, ValueError):
                # Fallback for platforms where add_signal_handler is unavailable
                try:
                    signal.signal(sig, lambda s, f: _request_shutdown())
                except (OSError, ValueError):
                    pass

        try:
            await _run_all()
        finally:
            if self._config_watch_task:
                self._config_watch_task.cancel()
            if self._scheduler_task:
                self._scheduler_task.cancel()
            await self.stop_channels()
