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
from praisonaiagents.session.protocols import SessionStoreProtocol
from praisonaiagents.session.store import DefaultSessionStore

logger = logging.getLogger(__name__)

from .unicode_utils import safe_error_message, safe_log_message, extract_root_cause_from_error
from .supervisor import ChannelSupervisor


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
    _event_cursor: int = 0  # Monotonic cursor for event replay
    _events: List[GatewayEvent] = field(default_factory=list)  # Event history for replay
    _was_resumed: bool = False  # Track if session was resumed from persistence
    
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
    
    def add_event(self, event: GatewayEvent) -> int:
        """Add an event and return its cursor position."""
        self._event_cursor += 1
        event.data['cursor'] = self._event_cursor
        self._events.append(event)
        self._last_activity = time.time()
        # Keep events bounded to prevent unbounded growth
        if len(self._events) > self._max_messages * 2:
            self._events = self._events[-self._max_messages:]
        return self._event_cursor
    
    def get_events_since(self, cursor: int) -> List[GatewayEvent]:
        """Get events since the given cursor."""
        return [e for e in self._events if e.data.get('cursor', 0) > cursor]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary for persistence."""
        # Drain inbox queue to a list for serialization
        pending_inbox = []
        temp_items = []
        while not self._inbox.empty():
            try:
                item = self._inbox.get_nowait()
                temp_items.append(item)
                pending_inbox.append(item)
            except asyncio.QueueEmpty:
                break
        
        # Put items back into the queue to preserve order
        for item in temp_items:
            self._inbox.put_nowait(item)
        
        return {
            "session_id": self._session_id,
            "agent_id": self._agent_id,
            "client_id": self._client_id,
            "is_active": self._is_active,
            "created_at": self._created_at,
            "last_activity": self._last_activity,
            "state": self._state,
            "messages": [{
                "content": msg.content,
                "sender_id": msg.sender_id,
                "session_id": msg.session_id,
                "message_id": msg.message_id,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata,
            } for msg in self._messages],
            "event_cursor": self._event_cursor,
            "events": [e.to_dict() for e in self._events[-100:]],  # Keep last 100 events
            "pending_inbox": pending_inbox,
            "is_executing": self._is_executing,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_messages: int = 1000) -> 'GatewaySession':
        """Deserialize session from dictionary."""
        session = cls(
            _session_id=data["session_id"],
            _agent_id=data["agent_id"],
            _client_id=data.get("client_id"),
            _is_active=data.get("is_active", True),
            _created_at=data.get("created_at", time.time()),
            _last_activity=data.get("last_activity", time.time()),
            _state=data.get("state", {}),
            _max_messages=max_messages,
        )
        
        # Mark this session as resumed from persistence
        session._was_resumed = True
        
        # Restore messages
        for msg_data in data.get("messages", []):
            msg = GatewayMessage(
                content=msg_data["content"],
                sender_id=msg_data["sender_id"],
                session_id=msg_data["session_id"],
                message_id=msg_data.get("message_id"),
                timestamp=msg_data.get("timestamp", time.time()),
                metadata=msg_data.get("metadata", {}),
            )
            session._messages.append(msg)
        
        # Restore event cursor and events
        session._event_cursor = data.get("event_cursor", 0)
        for event_data in data.get("events", []):
            event = GatewayEvent.from_dict(event_data)
            session._events.append(event)
        
        # Restore pending inbox messages
        for message in data.get("pending_inbox", []):
            session._inbox.put_nowait(message)
        
        # Restore execution state
        session._is_executing = data.get("is_executing", False)
        
        return session

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
        
        with open(config_path, "r", encoding="utf-8") as f:
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
        
        # Build GatewayConfig with session configuration
        from praisonaiagents.gateway.config import SessionConfig
        
        # Parse session configuration if present
        session_config = SessionConfig()
        if "session" in gateway_config:
            session_data = gateway_config["session"]
            session_config = SessionConfig(
                timeout=int(session_data.get("timeout", 3600)),
                max_messages=int(session_data.get("max_messages", 1000)),
                persist=bool(session_data.get("persist", False)),
                persist_path=_substitute(session_data.get("persist_path")),
                resume_window=int(session_data.get("resume_window", 86400)),
            )
        
        config = GatewayConfig(
            host=_substitute(gateway_config.get("host", "127.0.0.1")),
            port=int(gateway_config.get("port", 8765)),
            auth_token=_substitute(gateway_config.get("auth_token")),
            allowed_origins=gateway_config.get("allowed_origins", []),
            max_connections=int(gateway_config.get("max_connections", 1000)),
            heartbeat_interval=int(gateway_config.get("heartbeat_interval", 30)),
            reconnect_timeout=int(gateway_config.get("reconnect_timeout", 60)),
            ssl_cert=_substitute(gateway_config.get("ssl_cert")),
            ssl_key=_substitute(gateway_config.get("ssl_key")),
            session_config=session_config,
        )
        
        logger.info(f"Gateway config loaded from {config_path}")
        return cls(config=config)
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        config: Optional[GatewayConfig] = None,
        session_store: Optional[SessionStoreProtocol] = None,
    ):
        """Initialize the gateway.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            config: Optional gateway configuration
            session_store: Optional session store for persistence
        """
        self.config = config or GatewayConfig(host=host, port=port)
        
        # Set bind_host for bind-aware authentication
        self.config.bind_host = self.config.host
        
        if hasattr(self.config, 'auth_token') and not self.config.auth_token:
            # Prefer a user-configured token (persisted by `praisonai onboard`
            # to ~/.praisonai/.env as GATEWAY_AUTH_TOKEN) so the dashboard
            # URL stays stable across daemon restarts. Only fall back to
            # generating a random ephemeral token if nothing is set.
            env_tok = os.environ.get("GATEWAY_AUTH_TOKEN", "").strip()
            if env_tok:
                self.config.auth_token = env_tok
                logger.info("Gateway using GATEWAY_AUTH_TOKEN from environment")
            else:
                import secrets
                from praisonaiagents.gateway.protocols import is_loopback
                from .auth import get_auth_token_fingerprint, save_auth_token_to_env

                if is_loopback(self.config.bind_host):
                    self.config.auth_token = secrets.token_hex(16)
                    fingerprint = get_auth_token_fingerprint(self.config.auth_token)
                    logger.warning(
                        f"No auth_token provided for Gateway server. Generated temporary token: {fingerprint}. "
                        "For production, set GATEWAY_AUTH_TOKEN."
                    )

                    # Save to ~/.praisonai/.env for future use
                    try:
                        save_auth_token_to_env(self.config.auth_token)
                    except Exception as e:
                        logger.debug(f"Could not save auth token to .env: {e}")
        
        # Ensure single source of truth: export resolved token so all auth paths use the same secret
        if self.config.auth_token:
            os.environ["GATEWAY_AUTH_TOKEN"] = self.config.auth_token
        
        # Load allowed origins from environment if not set
        if hasattr(self.config, 'allowed_origins') and not self.config.allowed_origins:
            env_origins = os.environ.get("GATEWAY_ALLOWED_ORIGINS", "").strip()
            if env_origins:
                # Split by comma and clean up whitespace
                self.config.allowed_origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
                logger.info(f"Gateway using GATEWAY_ALLOWED_ORIGINS from environment: {self.config.allowed_origins}")
        
        self._host = self.config.host
        self._port = self.config.port
        
        self._is_running = False
        self._started_at: Optional[float] = None
        self._server = None
        
        self._agents: Dict[str, "Agent"] = {}
        self._sessions: Dict[str, GatewaySession] = {}
        self._clients: Dict[str, Any] = {}  # WebSocket connections
        self._client_sessions: Dict[str, str] = {}  # client_id -> session_id
        
        # Initialize session store based on configuration
        if session_store:
            self._session_store: Optional[SessionStoreProtocol] = session_store
        elif self.config.session_config.persist:
            # Use DefaultSessionStore when persistence is enabled
            persist_path = self.config.session_config.persist_path
            self._session_store = DefaultSessionStore(session_dir=persist_path)
            logger.info(f"Session persistence enabled, using directory: {persist_path or '~/.praisonai/sessions/'}")
        else:
            self._session_store = None
            logger.info("Session persistence disabled, using in-memory sessions only")
        
        # Track session TTLs for cleanup
        self._session_ttls: Dict[str, float] = {}  # session_id -> expiry timestamp
        
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Multi-bot lifecycle
        self._channel_bots: Dict[str, Any] = {}  # channel_name -> bot instance
        self._routing_rules: Dict[str, Dict[str, str]] = {}  # channel_name -> {context -> agent_id}
        self._channel_tasks: List[asyncio.Task] = []
        
        # Pairing store for channel authorization
        from .pairing import PairingStore
        self.pairing_store = PairingStore()
        
        # Scheduler tick background task
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Session cleanup background task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # PID lock for single-instance enforcement
        self._pid_lock: Optional[Any] = None
        
        # Channel supervisor for resilient bot management
        self._channel_supervisor = ChannelSupervisor()
        self._health_config = None  # Will be set from config if provided
    
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
        
        # Preflight port collision check
        from .port_utils import check_port_available, GatewayPIDLock, format_collision_error
        
        pid_lock = GatewayPIDLock(host=self._host, port=self._port)
        
        # Check if port is available
        port_available, pid_using_port = check_port_available(self._host, self._port)
        if not port_available:
            # Check if we have a PID lock
            lock_info = pid_lock.get_lock_info()
            error_msg = format_collision_error(self._host, self._port, lock_info)
            logger.error("Gateway startup failed due to port collision")
            raise RuntimeError(error_msg)
        
        # Try to acquire PID lock
        if not pid_lock.acquire_lock(self._host, self._port):
            lock_info = pid_lock.get_lock_info()
            error_msg = format_collision_error(self._host, self._port, lock_info)
            logger.error("Gateway startup failed - another instance is running")
            raise RuntimeError(error_msg)
        
        # Store PID lock for cleanup
        self._pid_lock = pid_lock
        
        # Validate bind-aware auth configuration before starting
        from .auth import assert_external_bind_safe
        self.config.host = self._host
        self.config.port = self._port
        self.config.bind_host = self._host
        assert_external_bind_safe(self.config)

        # Import origin checking functionality
        from .origin_check import check_origin, is_loopback, GatewayStartupError

        # Validate allowed_origins configuration for external binds
        if not is_loopback(self._host) and not self.config.allowed_origins:
            logger.error("Gateway startup failed due to configuration error")
            raise GatewayStartupError(
                f"Gateway is binding to external interface '{self._host}' but no allowed_origins configured. "
                "Set GATEWAY_ALLOWED_ORIGINS environment variable or configure allowed_origins in gateway config. "
                "Example: GATEWAY_ALLOWED_ORIGINS=\"https://your-ui.example.com,https://localhost:3000\""
            )
        
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
            """Validate auth token if configured. Returns error response or None.

            Accepts either:
              - ``Authorization: Bearer <token>`` header (preferred for APIs)
              - ``?token=<token>`` query parameter (so the dashboard URL from
                ``praisonai onboard`` is clickable in a browser)
              - Cookie-based authentication (praisonai_session cookie)
            """
            if not self.config.auth_token:
                return None
            
            # Check for cookie authentication first
            try:
                from .cookie_auth import create_auth_manager_from_env
                auth_manager = create_auth_manager_from_env()
                if auth_manager:
                    cookie_header = request.headers.get("cookie", "")
                    token_from_cookie = auth_manager.extract_token_from_cookies(cookie_header)
                    if token_from_cookie and auth_manager.is_token_valid(token_from_cookie):
                        return None  # Authenticated via cookie
            except ImportError:
                pass
            
            # Check loopback bypass for local requests (only if explicitly enabled)
            allow_loopback = os.environ.get("ALLOW_LOOPBACK_BYPASS", "").lower() in ("true", "1", "yes")
            if allow_loopback:
                client_host = getattr(request.client, 'host', None) if request.client else None
                if client_host and client_host in ('127.0.0.1', '::1', 'localhost'):
                    # Reject if proxy headers are present (indicates request went through proxy)
                    proxy_headers = ["x-forwarded-for", "via", "x-real-ip", "x-forwarded-host"]
                    has_proxy_headers = any(header in request.headers for header in proxy_headers)
                    if not has_proxy_headers:
                        # Allow local requests without auth for development
                        return None
            
            # Fall back to token-based auth
            auth_header = request.headers.get("authorization", "")
            token: str = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            else:
                token = request.query_params.get("token", "")
                if token:
                    import warnings
                    warnings.warn(
                        "DeprecationWarning: Use Sec-WebSocket-Protocol or magic link cookie",
                        DeprecationWarning,
                        stacklevel=2
                    )
            
            if not token:
                return JSONResponse(
                    {"error": "Authentication required. Please use your magic link."},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
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
            # Get client IP for rate limiting
            client_ip = websocket.client.host if websocket.client else "unknown"

            # Rate limiting for WebSocket upgrades (exempt loopback per acceptance criteria)
            if not is_loopback(client_ip) and not is_loopback(self._host):
                if not _ws_upgrade_rate.allow("ws_upgrade", client_ip):
                    retry = _ws_upgrade_rate.time_until_allowed("ws_upgrade", client_ip)
                    await websocket.close(code=4008, reason="Rate limited")
                    logger.warning(f"WebSocket upgrade rate limited for {client_ip} (retry in {retry:.0f}s)")
                    return

            # Origin validation (CSWSH defense)
            origin = websocket.headers.get("origin")
            try:
                if not check_origin(origin, self.config.allowed_origins, self._host):
                    await websocket.close(code=4003, reason="Origin not allowed")
                    logger.warning(f"WebSocket connection rejected: origin '{origin}' not in allowed list")
                    return
            except GatewayStartupError as e:
                await websocket.close(code=4003, reason="Configuration error")
                logger.error(f"WebSocket connection failed due to configuration error: {e}")
                return

            # Authenticate WebSocket via session cookie or query param
            if self.config.auth_token:
                authenticated = False
                
                # First try cookie-based authentication
                try:
                    from .cookie_auth import CookieAuthManager
                    auth_manager = CookieAuthManager(secret_key=self.config.auth_token)
                    cookie_header = websocket.headers.get("cookie", "")
                    token_from_cookie = auth_manager.extract_token_from_cookies(cookie_header)
                    if token_from_cookie and auth_manager.is_token_valid(token_from_cookie):
                        authenticated = True
                except ImportError:
                    pass
                
                # Fall back to query param token authentication
                if not authenticated:
                    ws_token = websocket.query_params.get("token", "")
                    if ws_token and secrets.compare_digest(ws_token, self.config.auth_token):
                        authenticated = True
                
                if not authenticated:
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
        from .pairing_routes import create_pairing_routes

        _approval_mgr = get_exec_approval_manager()
        _approval_rate = AuthRateLimiter(max_attempts=10, window_seconds=60)
        _ws_upgrade_rate = AuthRateLimiter(max_attempts=10, window_seconds=60)

        # Create pairing routes
        _pairing_routes = create_pairing_routes(self.pairing_store, _check_auth, _approval_rate)

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

        # ── Magic Link Authentication ────────────────────────────────────
        from .magic_link import MagicLinkStore
        from .cookie_auth import create_auth_manager_from_env
        from .rate_limiter import AuthRateLimiter
        
        # Initialize magic link store and rate limiter
        _magic_store = MagicLinkStore()
        _magic_rate = AuthRateLimiter(max_attempts=5, window_seconds=60)
        
        async def magic_link_handler(request):
            """Handle GET /?link=<nonce> magic link authentication."""
            nonce = request.query_params.get("link", "")
            if not nonce:
                # No magic link, redirect to auth required page or return 401
                return JSONResponse(
                    {"error": "Authentication required. Get a fresh link: praisonai gateway mint-link"},
                    status_code=401
                )
            
            client_ip = request.client.host if request.client else "unknown"
            if not _magic_rate.allow("magic_link", client_ip):
                retry = _magic_rate.time_until_allowed("magic_link", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )
            
            # Try to consume the nonce
            if not _magic_store.consume(nonce):
                return JSONResponse(
                    {"error": "This link was already used or has expired. Get a fresh one: praisonai gateway mint-link"},
                    status_code=401
                )
            
            # Create session cookie
            try:
                auth_manager = create_auth_manager_from_env()
                if not auth_manager:
                    return JSONResponse(
                        {"error": "Cookie authentication not available"},
                        status_code=500
                    )
                
                session_token = auth_manager.create_session(
                    user_id="gateway_user",
                    auth_method="magic_link"
                )
                
                # Determine if HTTPS
                is_https = (
                    request.headers.get("x-forwarded-proto") == "https" or
                    request.url.scheme == "https"
                )
                
                cookie_header = auth_manager.create_cookie_header(
                    session_token,
                    secure=is_https,
                    http_only=True,
                    same_site="Strict"
                )
                
                # Redirect to remove the nonce from URL
                from starlette.responses import RedirectResponse
                response = RedirectResponse(
                    url=str(request.url.replace(query="")),
                    status_code=302
                )
                response.headers["Set-Cookie"] = cookie_header
                return response
                
            except ImportError:
                return JSONResponse(
                    {"error": "Cookie authentication dependencies not available"},
                    status_code=500
                )
        
        # Channel control endpoints
        async def pause_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/pause — pause a channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            channel_name = request.path_params["name"]
            success = self.pause_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'paused' if success else 'could not be paused'}"
            })
        
        async def resume_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/resume — resume a paused channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            channel_name = request.path_params["name"]
            success = self.resume_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'resumed' if success else 'could not be resumed'}"
            })
        
        async def reconnect_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/reconnect — reconnect a channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            channel_name = request.path_params["name"]
            success = self.reconnect_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'reconnected' if success else 'could not be reconnected'}"
            })
        
        routes = [
            Route("/", magic_link_handler, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/api/approval/pending", approval_pending, methods=["GET"]),
            Route("/api/approval/resolve", approval_resolve, methods=["POST"]),
            Route("/api/approval/allow-list", approval_allowlist, methods=["GET", "POST", "DELETE"]),
            Route("/api/pairing/pending", _pairing_routes["pending"], methods=["GET"]),
            Route("/api/pairing/approve", _pairing_routes["approve"], methods=["POST"]),
            Route("/api/pairing/revoke", _pairing_routes["revoke"], methods=["POST"]),
            Route("/api/channels/{name}/pause", pause_channel_handler, methods=["POST"]),
            Route("/api/channels/{name}/resume", resume_channel_handler, methods=["POST"]),
            Route("/api/channels/{name}/reconnect", reconnect_channel_handler, methods=["POST"]),
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
        
        # Start session cleanup task if persistence is enabled
        if self._session_store:
            await self._start_session_cleanup()
        
        logger.info(f"Gateway started on ws://{self._host}:{self._port}")
        
        try:
            await self._server.serve()
        except Exception as e:
            # Clean up PID lock on any startup failure
            if hasattr(self, '_pid_lock') and self._pid_lock:
                self._pid_lock.release_lock()
                self._pid_lock = None
            # Re-raise the original exception
            raise
    
    async def _drain_active_sessions(self, reason: str = "shutdown", timeout: float = 10.0) -> None:
        """Drain active sessions by waiting for in-flight executions to complete.
        
        Args:
            reason: Reason for draining (e.g., "shutdown", "restart")
            timeout: Maximum time to wait for sessions to complete
        """
        active_sessions = [
            session for session in self._sessions.values()
            if session._is_executing or not session._inbox.empty()
        ]
        
        if not active_sessions:
            return
        
        logger.info(f"Draining {len(active_sessions)} active sessions (reason: {reason})")
        
        # Give sessions time to complete
        start_time = asyncio.get_event_loop().time()
        while active_sessions and (asyncio.get_event_loop().time() - start_time) < timeout:
            # Check which sessions are still active
            still_active = []
            for session in active_sessions:
                if session._is_executing or not session._inbox.empty():
                    still_active.append(session)
                else:
                    # Session completed, persist it
                    if self._session_store:
                        try:
                            self._session_store.add_message(
                                session_id=session.session_id,
                                role="system",
                                content=f"Session drained: {reason}",
                                metadata={"session_data": session.to_dict()},
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist drained session {session.session_id}: {e}")
            
            active_sessions = still_active
            if active_sessions:
                await asyncio.sleep(0.5)  # Brief wait before checking again
        
        # For any remaining active sessions, persist them as-is with pending work
        for session in active_sessions:
            logger.warning(f"Session {session.session_id} still active after drain timeout, persisting with pending work")
            if self._session_store:
                try:
                    # Add a session_end event before persisting
                    session.add_event(GatewayEvent(
                        type=EventType.SESSION_END,
                        data={
                            "session_id": session.session_id,
                            "reason": f"Force-closed during {reason} after timeout",
                            "had_pending_work": not session._inbox.empty(),
                            "was_executing": session._is_executing,
                        }
                    ))
                    
                    self._session_store.add_message(
                        session_id=session.session_id,
                        role="system",
                        content=f"Session force-closed during {reason} with pending work",
                        metadata={"session_data": session.to_dict()},
                    )
                except Exception as e:
                    logger.error(f"Failed to persist timed-out session {session.session_id}: {e}")

    async def stop(self, drain_timeout: float = 10.0) -> None:
        """Stop the gateway server with graceful drain.
        
        Args:
            drain_timeout: Maximum time to wait for active sessions to complete (default: 10.0)
        """
        if not self._is_running:
            return
        
        self._is_running = False
        
        # Gracefully drain active sessions before closing
        await self._drain_active_sessions(reason="shutdown", timeout=drain_timeout)
        
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
        
        # Release PID lock
        if hasattr(self, '_pid_lock') and self._pid_lock:
            self._pid_lock.release_lock()
        
        logger.info("Gateway stopped")
    
    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]) -> None:
        """Handle a message from a client."""
        msg_type = data.get("type", "message")
        
        if msg_type == "join":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agents:
                # Support reconnection with existing session
                session_id = data.get("session_id")  # Optional: existing session to resume
                since_cursor = data.get("since")  # Optional: cursor for event replay
                
                # Resume or create session
                session, replay_events = self.resume_or_create_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    client_id=client_id,
                    since_cursor=since_cursor,
                )
                
                self._client_sessions[client_id] = session.session_id
                
                # Send join confirmation
                await self._send_to_client(client_id, {
                    "type": "joined",
                    "session_id": session.session_id,
                    "agent_id": agent_id,
                    "resumed": session._was_resumed,
                    "cursor": session._event_cursor,
                })
                
                # Replay missed events if any
                for event in replay_events:
                    await self._send_to_client(client_id, {
                        "type": "replay",
                        "event": event.to_dict(),
                    })
                
                # If session was resumed with pending messages or was executing, restart processing
                if session._was_resumed and (not session._inbox.empty() or session._is_executing):
                    agent = self._agents.get(agent_id)
                    if agent:
                        logger.info(f"Resuming processing for session {session.session_id} with {session._inbox.qsize()} pending messages")
                        # Notify client that we're resuming processing
                        await self._send_to_client(client_id, {
                            "type": "status",
                            "source": session.agent_id,
                            "message": f"Resuming processing ({session._inbox.qsize()} pending messages)...",
                        })
                        # Restart the queue processor
                        asyncio.create_task(self._run_session_queue(session, agent, client_id))
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
                # Close session but keep it persisted for resumption
                self.close_session(session_id, persist=True)
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
        """Create a StreamCallback that relays events to a WS client."""
        gateway = self
        # Capture the running loop while we are still on it.
        loop = asyncio.get_running_loop()

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
                
                # No get_event_loop() in the threaded callback.
                asyncio.run_coroutine_threadsafe(
                    gateway._send_to_client(client_id, gw_event.to_dict()),
                    loop,
                )
            except Exception:
                logger.warning("Stream relay error (non-fatal)", exc_info=True)

        return _relay
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to a specific client."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                # Track event in session BEFORE sending if it's a response or important event
                if data.get("type") in ["response", "message", "stream_end", "error"]:
                    session_id = self._client_sessions.get(client_id)
                    if session_id:
                        session = self._sessions.get(session_id)
                        if session:
                            event = GatewayEvent(
                                type=data.get("type", "message"),
                                data=data,
                                source="gateway",
                                target=client_id,
                            )
                            cursor = session.add_event(event)
                            # Add cursor to the data BEFORE sending
                            data["cursor"] = cursor
                
                # Send ONCE with cursor already attached if applicable
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
        """Create a new session or resume an existing one."""
        sid = session_id or str(uuid.uuid4())
        
        # Check if session exists in memory first
        if sid in self._sessions:
            session = self._sessions[sid]
            if session.is_active:
                logger.info(f"Session already active in memory: {sid}")
                return session
        
        # Try to rehydrate from persistent store
        if session_id and self._session_store and self._session_store.session_exists(session_id):
            try:
                # Rehydrate session from store - get full session data with metadata
                session_data_obj = self._session_store.get_session(session_id)
                
                # Load session metadata if stored
                session_data = None
                
                # Try to extract session data from system messages with metadata
                for msg in session_data_obj.messages:
                    if msg.role == 'system' and msg.metadata and 'session_data' in msg.metadata:
                        session_data = msg.metadata['session_data']
                        break
                
                # Restore session from persisted data
                if session_data:
                    session = GatewaySession.from_dict(session_data, self.config.session_config.max_messages)
                else:
                    # Fallback: create new session but restore messages
                    session = GatewaySession(
                        _session_id=sid,
                        _agent_id=agent_id,
                        _client_id=client_id,
                        _max_messages=self.config.session_config.max_messages,
                    )
                    # Mark as resumed since we're restoring from persistence
                    session._was_resumed = True
                    # Restore messages from history
                    for msg in session_data_obj.messages:
                        if msg.role in ['user', 'assistant']:
                            gateway_msg = GatewayMessage(
                                content=msg.content,
                                sender_id=msg.role,
                                session_id=sid,
                                timestamp=msg.timestamp,
                                metadata=msg.metadata or {},
                            )
                            session.add_message(gateway_msg)
                
                session._is_active = True  # Reactivate the session
                self._sessions[sid] = session
                logger.info(f"Session resumed from persistent store: {sid} for agent {agent_id}")
                return session
            except Exception as e:
                logger.warning(f"Failed to rehydrate session {sid}: {e}. Creating new session.")
        
        # Create new session
        session = GatewaySession(
            _session_id=sid,
            _agent_id=agent_id,
            _client_id=client_id,
            _max_messages=self.config.session_config.max_messages,
        )
        self._sessions[sid] = session
        
        # Persist initial session state if store is configured
        if self._session_store:
            try:
                # Store session metadata as first system message
                self._session_store.add_message(
                    session_id=sid,
                    role="system",
                    content="Session initialized",
                    metadata={"session_data": session.to_dict()},
                )
            except Exception as e:
                logger.warning(f"Failed to persist initial session state: {e}")
        
        logger.info(f"Session created: {sid} for agent {agent_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[GatewaySession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def close_session(self, session_id: str, persist: bool = True) -> bool:
        """Close a session, optionally persisting it for later resumption.
        
        Args:
            session_id: The session ID to close
            persist: Whether to persist the session for later resumption (default: True)
        
        Returns:
            True if session was closed, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.close()
        
        # Persist session state before removing from memory if configured
        if persist and self._session_store:
            try:
                # Save final session state
                self._session_store.add_message(
                    session_id=session_id,
                    role="system",
                    content="Session closed",
                    metadata={"session_data": session.to_dict()},
                )
                # Set TTL for session cleanup
                resume_window = self.config.session_config.resume_window
                self._session_ttls[session_id] = time.time() + resume_window
                logger.info(f"Session {session_id} persisted, resumable for {resume_window}s")
            except Exception as e:
                logger.warning(f"Failed to persist session state on close: {e}")
        
        # Remove from active sessions
        self._sessions.pop(session_id, None)
        
        logger.info(f"Session closed: {session_id}")
        return True
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        if agent_id:
            return [
                sid for sid, session in self._sessions.items()
                if session.agent_id == agent_id
            ]
        return list(self._sessions.keys())
    
    def resume_or_create_session(
        self,
        session_id: Optional[str],
        agent_id: str,
        client_id: Optional[str] = None,
        since_cursor: Optional[int] = None,
    ) -> tuple[GatewaySession, List[GatewayEvent]]:
        """Resume an existing session or create a new one, with event replay.
        
        Args:
            session_id: Existing session ID to resume (None to create new)
            agent_id: Agent ID for the session
            client_id: Client ID
            since_cursor: Cursor position to replay events from
        
        Returns:
            Tuple of (session, replay_events) where replay_events are events
            that occurred after since_cursor
        """
        replay_events = []
        
        # Try to resume existing session
        if session_id:
            session = self.get_session(session_id)
            if not session and self._session_store and self._session_store.session_exists(session_id):
                # Rehydrate from store
                session = self.create_session(agent_id, client_id, session_id)
            
            if session:
                # Get events to replay if cursor provided
                if since_cursor is not None:
                    replay_events = session.get_events_since(since_cursor)
                    logger.info(f"Replaying {len(replay_events)} events since cursor {since_cursor}")
                return session, replay_events
        
        # Create new session if not found
        session = self.create_session(agent_id, client_id, session_id)
        return session, []
    
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
        """Get gateway health status including per-channel bot status and supervision state."""
        uptime = time.time() - self._started_at if self._started_at else 0
        channel_status = {}
        supervision_status = self._channel_supervisor.get_all_status()
        
        for name, bot in self._channel_bots.items():
            running = getattr(bot, "is_running", False)
            platform = getattr(bot, "platform", "unknown")
            
            # Get supervision state
            sup_status = supervision_status.get(name)
            if sup_status:
                channel_status[name] = {
                    "platform": platform,
                    "running": running,
                    "supervision": {
                        "state": sup_status.state.value,
                        "last_error": sup_status.last_error,
                        "last_error_time": sup_status.last_error_time,
                        "next_retry_at": sup_status.next_retry_at,
                        "total_recoveries": sup_status.total_recoveries,
                        "manual_pause": sup_status.manual_pause,
                    }
                }
            else:
                channel_status[name] = {
                    "platform": platform,
                    "running": running,
                }
                
        result = {
            "status": "healthy" if self._is_running else "stopped",
            "uptime": uptime,
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "clients": len(self._clients),
            "channels": channel_status,
        }
        
        # Add push status if enabled (push infra lives in wrapper; guard defensively)
        if getattr(self, "_push_enabled", False):
            push_status: Dict[str, Any] = {"enabled": True}
            channel_mgr = getattr(self, "_channel_mgr", None)
            if channel_mgr is not None:
                push_status["push_channels"] = len(channel_mgr.list_channels())
            presence_mgr = getattr(self, "_presence_mgr", None)
            if presence_mgr is not None:
                push_status["online_clients"] = presence_mgr.get_online_count()
            redis_pubsub = getattr(self, "_redis_pubsub", None)
            if redis_pubsub is not None:
                push_status["redis_connected"] = getattr(redis_pubsub, "_client", None) is not None
            result["push"] = push_status
        
        return result

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
    
    async def _start_session_cleanup(self) -> None:
        """Start periodic cleanup of expired sessions."""
        if not self._session_store:
            return  # No cleanup needed without persistence
        
        async def _cleanup():
            while self._is_running:
                try:
                    await asyncio.sleep(3600)  # Check hourly
                    
                    # Clean up expired session TTLs
                    current_time = time.time()
                    expired_sessions = [
                        sid for sid, expiry in self._session_ttls.items()
                        if expiry < current_time
                    ]
                    
                    for sid in expired_sessions:
                        try:
                            # Remove from TTL tracking
                            self._session_ttls.pop(sid, None)
                            
                            # Delete from persistent store
                            if self._session_store:
                                self._session_store.delete_session(sid)
                                logger.info(f"Expired session removed from store: {sid}")
                        except Exception as e:
                            logger.warning(f"Failed to cleanup expired session {sid}: {e}")
                            
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
        
        self._cleanup_task = asyncio.create_task(_cleanup())
        logger.info("Session cleanup task started (interval=1h)")

    # ── Multi-bot lifecycle ───────────────────────────────────────────

    @staticmethod
    def _substitute_env_vars(value: str) -> str:
        """Replace ``${VAR_NAME}`` patterns with environment variable values.

        Previously, missing env vars returned the literal ``${VAR_NAME}`` which
        caused downstream APIs (e.g. Telegram) to receive a broken token
        string and fail with opaque 404s. We now substitute missing vars with
        an **empty string** so the schema validator's required-field checks
        (e.g. ``token`` must be truthy) trip cleanly instead.
        """
        if not isinstance(value, str):
            return value
        def _replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                logger.warning(
                    f"Environment variable {var_name} not set "
                    f"— substituting empty string. "
                    f"Run `praisonai onboard` or set it in ~/.praisonai/.env."
                )
                return ""
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

        with open(config_path, "r", encoding="utf-8") as f:
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
        - reflection: Enable reflection/interactive mode (default: False)
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
            # Track if tools key was explicitly set (even as empty list) vs omitted
            tools_key_present = "tools" in agent_def
            explicit_empty_tools = tools_key_present and not agent_def.get("tools")
            
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

            # Additional agent options from YAML.
            tool_choice = agent_def.get("tool_choice", None)
            
            # reflection defaults to False for gateway agents: chat channels
            # (Telegram/Discord/Slack/WhatsApp) expect sub-second replies, and
            # self-reflection adds 1-N extra LLM round-trips per message
            # (~8x latency for short prompts on gpt-4o-mini). Users who want
            # higher answer quality can opt in with `reflection: true` in YAML.
            reflection = agent_def.get("reflection", False)
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
            
            # Store explicit empty tools flag to prevent smart defaults injection
            if explicit_empty_tools:
                agent._explicit_empty_tools = True

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

            # Extract allowlist configuration from channel config  
            _raw_allowed = ch_cfg.get("allowed_users") or []
            if isinstance(_raw_allowed, str):
                # Env-expanded string like "12345,67890"; split on commas.
                _raw_allowed = [s.strip() for s in _raw_allowed.split(",") if s.strip()]

            _raw_channels = ch_cfg.get("allowed_channels") or []
            if isinstance(_raw_channels, str):
                _raw_channels = [s.strip() for s in _raw_channels.split(",") if s.strip()]

            # Extract group policy setting
            group_policy = ch_cfg.get("group_policy", "mention_only")
            mention_required = (group_policy == "mention_only")

            # Extract auto_approve_tools setting (default True for chat bots)
            _raw_auto_approve = ch_cfg.get("auto_approve_tools")
            if _raw_auto_approve is None:
                auto_approve_tools = True   # SAFE-DEFAULT: safe tools auto-approved in chat
            elif isinstance(_raw_auto_approve, str):
                auto_approve_tools = _raw_auto_approve.strip().lower() in ("1", "true", "yes", "on")
            else:
                auto_approve_tools = bool(_raw_auto_approve)

            config_kwargs = dict(
                token=token,
                allowed_users=list(_raw_allowed),
                allowed_channels=list(_raw_channels),
                mention_required=mention_required,
                group_policy=group_policy,
                auto_approve_tools=auto_approve_tools,
            )
            
            # Only pass default_tools when the channel explicitly overrides it,
            # so BotConfig's own default_factory stays the single source of truth.
            _raw_yaml_tools = ch_cfg.get("default_tools")
            if isinstance(_raw_yaml_tools, list):
                config_kwargs["default_tools"] = _raw_yaml_tools
            
            config = BotConfig(**config_kwargs)

            # Warn if no allowlist is configured
            if not config.allowed_users:
                logger.warning(
                    "Channel %r has no allowed_users — bot accepts messages from everyone. "
                    "Re-run `praisonai onboard` to configure.",
                    channel_name,
                )

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
            # Start health monitoring if configured
            if self._health_config and self._health_config.enabled:
                await self._channel_supervisor.start_health_monitoring()
                logger.info("Channel health monitoring enabled")
            
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
        # Clone agent to prevent channel-specific settings from leaking between channels
        # Use clone_for_channel() instead of copy.deepcopy() to avoid RLock issues (fixes #1746)
        agent = agent.clone_for_channel()
        
        # Apply smart defaults to agent (same logic as Bot() wrapper)
        from praisonai.bots._defaults import apply_bot_smart_defaults
        agent = apply_bot_smart_defaults(agent, config)

        # Check if agent ended up with zero tools after defaults and warn
        current_tools = getattr(agent, 'tools', None) or []
        if not current_tools:
            logger.warning(
                "Bot for channel %r started with zero tools — chat will be text-only. "
                "Check that `praisonaiagents.tools` is installed and that "
                "`tools: []` is not set explicitly in bot.yaml.",
                ch_cfg.get('platform', channel_type),
            )

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
        elif channel_type == "linear":
            from praisonai.bots import LinearBot
            linear_token = token or os.environ.get("LINEAR_OAUTH_TOKEN", "") or os.environ.get("LINEAR_API_KEY", "")
            return LinearBot(
                token=linear_token,
                agent=agent,
                config=config,
                signing_secret=ch_cfg.get("signing_secret", "") or os.environ.get("LINEAR_WEBHOOK_SECRET", ""),
                webhook_port=int(ch_cfg.get("webhook_port", 8080)),
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
        """Run a single bot with supervision and resilient error handling.

        Uses the channel supervisor for unlimited retries with error classification,
        exponential backoff, and operator controls.
        """
        async def start_bot(name: str, bot: Any) -> None:
            """Start function for the supervisor."""
            # TelegramBot special handling: run_polling() tries to manage
            # its own event loop which conflicts with our gateway loop.
            # Use the lower-level API instead.
            if self._is_telegram_bot(bot):
                await self._start_telegram_bot_polling(name, bot)
            elif type(bot).__name__ in ("WhatsAppBot", "LinearBot"):
                # WhatsApp/Linear run their own aiohttp webhook servers
                self._inject_routing_handler(name, bot)
                await bot.start()
            else:
                # Inject routing-aware handler for Discord/Slack
                self._inject_routing_handler(name, bot)
                await bot.start()
        
        # Use supervisor for resilient channel management
        await self._channel_supervisor.run(name, bot, start_bot)

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
            # Import the shared security pipeline from telegram.py
            from praisonai.bots.telegram import process_inbound_telegram_message
            
            # Use shared security pipeline for consistent enforcement
            message = await process_inbound_telegram_message(update, bot)
            if not message:
                return  # Message was dropped by security checks

            user_id = message.sender.user_id if message.sender else "unknown"
            message_text = message.content

            # Determine routing context
            chat_type = update.message.chat.type if update.message.chat else "private"
            routing_ctx = gateway._determine_routing_context(
                "telegram", {"chat_type": chat_type}
            )
            agent = gateway._resolve_agent_for_message(channel_name, routing_ctx)
            if not agent:
                agent = bot._agent  # fallback to default

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
                
                # Show typing indicator with renewal during long operation
                if bot.config.typing_indicator:
                    from praisonai.bots._typing_indicator import with_typing_renewal
                    
                    async def _typing_action():
                        await update.message.chat.send_action("typing")
                    
                    response = await with_typing_renewal(
                        typing_func=_typing_action,
                        operation_coro=bot._session.chat(agent, user_id, message_text)
                    )
                else:
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
                logger.error(f"Agent error in {name}: {safe_log_message(e)}")
                user_error = extract_root_cause_from_error(str(e))
                await update.message.reply_text(f"Error: {safe_error_message(user_error)}")

        async def handle_voice(update: Update, context: Any):
            await handle_message(update, context)

        async def handle_status(update: Update, context: Any):
            if not update.message:
                return
            from praisonai.bots.telegram import process_inbound_telegram_message
            if not await process_inbound_telegram_message(update, bot):
                return
            await update.message.reply_text(bot._format_status())

        async def handle_new(update: Update, context: Any):
            if not update.message:
                return
            from praisonai.bots.telegram import process_inbound_telegram_message
            message = await process_inbound_telegram_message(update, bot)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            bot._session.reset(user_id)
            await update.message.reply_text("Session reset. Starting fresh conversation.")

        async def handle_help(update: Update, context: Any):
            if not update.message:
                return
            from praisonai.bots.telegram import process_inbound_telegram_message
            if not await process_inbound_telegram_message(update, bot):
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
        # Stop health monitoring first
        await self._channel_supervisor.stop_health_monitoring()
        
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

        # Clean up supervisor state for all channels
        for name in list(self._channel_bots.keys()):
            self._channel_supervisor.cleanup(name)

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

    # Channel supervision control methods
    
    def pause_channel(self, name: str) -> bool:
        """Pause a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was paused, False if not found or not running
        """
        return self._channel_supervisor.pause(name)
    
    def resume_channel(self, name: str) -> bool:
        """Resume a paused channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was resumed, False if not found or not paused
        """
        return self._channel_supervisor.resume(name)
    
    def reconnect_channel(self, name: str) -> bool:
        """Force reconnect a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel exists, False otherwise
        """
        return self._channel_supervisor.reconnect(name)
    
    def get_channel_supervision_status(self) -> Dict[str, Any]:
        """Get supervision status for all channels.
        
        Returns:
            Dictionary mapping channel names to their supervision status
        """
        status_dict = {}
        for name, status in self._channel_supervisor.get_all_status().items():
            status_dict[name] = {
                "state": status.state.value,
                "last_error": status.last_error,
                "last_error_time": status.last_error_time,
                "next_retry_at": status.next_retry_at,
                "total_recoveries": status.total_recoveries,
                "manual_pause": status.manual_pause,
            }
        return status_dict
    
    def get_health_monitor_status(self) -> Dict[str, Any]:
        """Get health monitor status.
        
        Returns:
            Dictionary with health monitor status and channel health information
        """
        return self._channel_supervisor.get_health_status()

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
        
        # Parse health monitoring configuration
        health_cfg = gw_cfg.get("health")
        if health_cfg and isinstance(health_cfg, dict):
            from .health_monitor import HealthMonitorConfig
            self._health_config = HealthMonitorConfig.from_dict(health_cfg)
            # Recreate supervisor with health config
            self._channel_supervisor = ChannelSupervisor(health_config=self._health_config)

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
            if self._cleanup_task:
                self._cleanup_task.cancel()
            await self.stop_channels()
