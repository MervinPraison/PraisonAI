"""
HTTP Stream Transport for MCP Server

Implements the MCP Streamable HTTP transport (MCP 2025-11-25 spec):
- Single endpoint for all MCP communication
- POST for client→server messages
- GET for server→client SSE stream (optional)
- Session management via MCP-Session-Id header
- Supports batch (JSON) and stream (SSE) response modes
- Origin header validation for security
- MCP-Protocol-Version header support
"""

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..server import MCPServer

logger = logging.getLogger(__name__)

# MCP Protocol Version (Updated to 2025-11-25)
PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_VERSIONS = ["2025-11-25", "2025-03-26"]


class HTTPStreamTransport:
    """
    HTTP Stream transport for MCP server.
    
    Implements the Streamable HTTP transport per MCP 2025-11-25 spec.
    """
    
    def __init__(
        self,
        server: "MCPServer",
        host: str = "127.0.0.1",
        port: int = 8080,
        endpoint: str = "/mcp",
        cors_origins: Optional[list] = None,
        allowed_origins: Optional[list] = None,
        api_key: Optional[str] = None,
        session_ttl: int = 3600,
        allow_client_termination: bool = True,
        response_mode: str = "batch",
        resumability_enabled: bool = True,
        event_history_duration: int = 300,
    ):
        """
        Initialize HTTP Stream transport.
        
        Args:
            server: MCPServer instance
            host: Server host
            port: Server port
            endpoint: MCP endpoint path
            cors_origins: CORS allowed origins
            allowed_origins: Origins allowed for security validation (None = localhost only)
            api_key: Optional API key for authentication
            session_ttl: Session TTL in seconds
            allow_client_termination: Allow client to terminate session via DELETE
            response_mode: Default response mode ("batch" or "stream")
            resumability_enabled: Enable SSE resumability
            event_history_duration: Duration to keep event history (seconds)
        """
        self.server = server
        self.host = host
        self.port = port
        self.endpoint = endpoint
        self.cors_origins = cors_origins or ["*"]
        self.api_key = api_key
        self.session_ttl = session_ttl
        self.allow_client_termination = allow_client_termination
        self.response_mode = response_mode
        self.resumability_enabled = resumability_enabled
        self.event_history_duration = event_history_duration
        
        # Allowed origins for security (MCP 2025-11-25 requirement)
        # Default: only localhost if binding to localhost
        if allowed_origins is None:
            if host in ("127.0.0.1", "localhost", "::1"):
                self.allowed_origins = ["http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1"]
            else:
                # External binding requires explicit origin config
                self.allowed_origins = None  # Will reject all Origin headers
                logger.warning("External binding without allowed_origins - Origin validation will reject all requests with Origin header")
        else:
            self.allowed_origins = allowed_origins
        
        # Session storage
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # SSE event history for resumability
        self._event_history: Dict[str, list] = {}
        self._event_counter = 0
        self._event_timestamps: Dict[str, float] = {}
    
    def run(self) -> None:
        """Run the HTTP Stream server."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError("uvicorn required. Install with: pip install uvicorn")
        
        app = self._create_app()
        
        logger.info(f"MCP server '{self.server.name}' starting on http://{self.host}:{self.port}{self.endpoint}")
        
        uvicorn.run(app, host=self.host, port=self.port, log_level="warning")
    
    def _validate_origin(self, request_origin: Optional[str]) -> bool:
        """
        Validate Origin header per MCP 2025-11-25 security requirements.
        
        Returns True if origin is valid or not present.
        Returns False if origin is present but invalid.
        """
        if request_origin is None:
            # No Origin header - allow (same-origin requests don't send Origin)
            return True
        
        if self.allowed_origins is None:
            # No allowed origins configured - reject all Origin headers
            return False
        
        # Check if origin matches any allowed origin
        for allowed in self.allowed_origins:
            if request_origin == allowed or request_origin.startswith(allowed):
                return True
        
        return False
    
    def _validate_protocol_version(self, version: Optional[str]) -> bool:
        """Validate MCP-Protocol-Version header."""
        if version is None:
            # No version header - assume 2025-03-26 for backwards compatibility
            return True
        return version in SUPPORTED_VERSIONS
    
    def _create_app(self) -> Any:
        """Create the Starlette/FastAPI application."""
        try:
            from starlette.applications import Starlette
            from starlette.middleware import Middleware
            from starlette.middleware.cors import CORSMiddleware
            from starlette.requests import Request
            from starlette.responses import JSONResponse, Response, StreamingResponse
            from starlette.routing import Route
        except ImportError:
            raise ImportError("starlette required. Install with: pip install starlette")
        
        async def mcp_post(request: Request) -> Response:
            """Handle POST requests (client→server messages)."""
            # Validate Origin header (MCP 2025-11-25 security requirement)
            origin = request.headers.get("Origin")
            if not self._validate_origin(origin):
                logger.warning(f"Rejected request with invalid Origin: {origin}")
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Forbidden: Invalid Origin"}},
                    status_code=403,
                )
            
            # Validate MCP-Protocol-Version header
            protocol_version = request.headers.get("MCP-Protocol-Version")
            if protocol_version and not self._validate_protocol_version(protocol_version):
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": f"Unsupported protocol version: {protocol_version}"}},
                    status_code=400,
                )
            
            # Check authentication
            if self.api_key:
                auth_header = request.headers.get("Authorization", "")
                if not auth_header.startswith("Bearer ") or auth_header[7:] != self.api_key:
                    return JSONResponse(
                        {"error": "Unauthorized"},
                        status_code=401,
                    )
            
            # Get or create session (check both header casings for compatibility)
            session_id = request.headers.get("MCP-Session-Id") or request.headers.get("Mcp-Session-Id")
            if session_id and session_id not in self._sessions:
                # Session expired
                return JSONResponse(
                    {"error": "Session not found"},
                    status_code=404,
                )
            
            # Parse request body
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                    status_code=400,
                )
            
            # Handle message
            response = await self.server.handle_message(body)
            
            # Check if this is an initialize request
            if body.get("method") == "initialize":
                # Create new session
                new_session_id = str(uuid.uuid4())
                self._sessions[new_session_id] = {
                    "created_at": time.time(),
                    "last_activity": time.time(),
                }
                
                # Add session ID to response headers (MCP 2025-11-25 uses MCP-Session-Id)
                headers = {
                    "MCP-Session-Id": new_session_id,
                    "MCP-Protocol-Version": PROTOCOL_VERSION,
                }
                
                if response:
                    return JSONResponse(response, headers=headers)
                return Response(status_code=202, headers=headers)
            
            # Update session activity
            if session_id and session_id in self._sessions:
                self._sessions[session_id]["last_activity"] = time.time()
            
            # Check Accept header for response mode
            accept = request.headers.get("Accept", "application/json")
            
            if "text/event-stream" in accept and response:
                # Stream mode - return SSE
                async def generate_sse():
                    event_id = self._next_event_id()
                    data = json.dumps(response)
                    yield f"id:{event_id}\ndata:{data}\n\n"
                
                return StreamingResponse(
                    generate_sse(),
                    media_type="text/event-stream",
                    headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
                )
            
            # Batch mode - return JSON
            if response:
                return JSONResponse(
                    response,
                    headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
                )
            
            return Response(
                status_code=202,
                headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
            )
        
        async def mcp_get(request: Request) -> Response:
            """Handle GET requests (server→client SSE stream)."""
            # Check both header casings for compatibility
            session_id = request.headers.get("MCP-Session-Id") or request.headers.get("Mcp-Session-Id")
            if not session_id or session_id not in self._sessions:
                return JSONResponse(
                    {"error": "Session required"},
                    status_code=400,
                )
            
            # Check for Last-Event-ID for resumability
            last_event_id = request.headers.get("Last-Event-ID")
            
            async def generate_sse():
                # If resuming, replay missed events
                if last_event_id and session_id in self._event_history:
                    history = self._event_history[session_id]
                    replay = False
                    for event_id, data in history:
                        if replay:
                            yield f"id:{event_id}\ndata:{data}\n\n"
                        elif event_id == last_event_id:
                            replay = True
                
                # Keep connection alive
                while True:
                    await asyncio.sleep(30)
                    yield ":keepalive\n\n"
            
            return StreamingResponse(
                generate_sse(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "MCP-Protocol-Version": PROTOCOL_VERSION,
                },
            )
        
        async def mcp_delete(request: Request) -> Response:
            """Handle DELETE requests (session termination)."""
            if not self.allow_client_termination:
                return Response(status_code=405)
            
            session_id = request.headers.get("MCP-Session-Id") or request.headers.get("Mcp-Session-Id")
            if session_id and session_id in self._sessions:
                del self._sessions[session_id]
                if session_id in self._event_history:
                    del self._event_history[session_id]
                return Response(status_code=204)
            
            return JSONResponse(
                {"error": "Session not found"},
                status_code=404,
            )
        
        async def mcp_options(request: Request) -> Response:
            """Handle OPTIONS requests for CORS preflight."""
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, MCP-Session-Id, Mcp-Session-Id, MCP-Protocol-Version, Mcp-Protocol-Version, Last-Event-ID",
                },
            )
        
        async def health(request: Request) -> Response:
            """Health check endpoint."""
            return JSONResponse({
                "status": "healthy",
                "server": self.server.name,
                "version": self.server.version,
                "protocol_version": PROTOCOL_VERSION,
                "active_sessions": len(self._sessions),
            })
        
        async def root(request: Request) -> Response:
            """Root endpoint."""
            return JSONResponse({
                "message": f"PraisonAI MCP Server: {self.server.name}",
                "mcp_endpoint": self.endpoint,
                "protocol_version": PROTOCOL_VERSION,
            })
        
        # Create routes
        routes = [
            Route(self.endpoint, mcp_post, methods=["POST"]),
            Route(self.endpoint, mcp_get, methods=["GET"]),
            Route(self.endpoint, mcp_delete, methods=["DELETE"]),
            Route(self.endpoint, mcp_options, methods=["OPTIONS"]),
            Route("/health", health, methods=["GET"]),
            Route("/", root, methods=["GET"]),
        ]
        
        # Create middleware
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=self.cors_origins,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["*"],
            ),
        ]
        
        return Starlette(routes=routes, middleware=middleware)
    
    def _next_event_id(self) -> str:
        """Generate next SSE event ID."""
        self._event_counter += 1
        return str(self._event_counter)
    
    def _cleanup_sessions(self) -> None:
        """Clean up expired sessions."""
        now = time.time()
        expired = [
            sid for sid, data in self._sessions.items()
            if now - data["last_activity"] > self.session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
            if sid in self._event_history:
                del self._event_history[sid]
