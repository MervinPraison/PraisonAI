"""
HTTP Server implementation for PraisonAI Agents.

Provides REST API and SSE event streaming.
"""

import asyncio
import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass
class ServerConfig:
    """Server configuration."""
    
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    auth_token: Optional[str] = None
    max_connections: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "auth_token": "***" if self.auth_token else None,
            "max_connections": self.max_connections,
        }


class SSEClient:
    """A Server-Sent Events client connection."""
    
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.queue: queue.Queue = queue.Queue()
        self.connected = True
        self.created_at = time.time()
    
    def send(self, event_type: str, data: Dict[str, Any]):
        """Send an event to this client."""
        if self.connected:
            self.queue.put({
                "event": event_type,
                "data": data,
                "id": str(uuid.uuid4()),
            })
    
    def disconnect(self):
        """Disconnect this client."""
        self.connected = False
    
    def events(self) -> Generator[str, None, None]:
        """Generate SSE formatted events."""
        while self.connected:
            try:
                event = self.queue.get(timeout=30)
                yield f"id: {event['id']}\n"
                yield f"event: {event['event']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except queue.Empty:
                # Send keepalive
                yield ": keepalive\n\n"


class AgentServer:
    """
    HTTP server for PraisonAI Agents.
    
    Provides REST API endpoints and SSE event streaming
    for real-time agent communication.
    
    Example:
        server = AgentServer(port=8080)
        
        # Register event handler
        @server.on_event("message")
        def handle_message(data):
            print(f"Message: {data}")
        
        # Start server
        server.start()
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        config: Optional[ServerConfig] = None,
    ):
        """
        Initialize the server.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            config: Optional server configuration
        """
        self.config = config or ServerConfig(host=host, port=port)
        self.host = self.config.host
        self.port = self.config.port
        
        self._clients: Dict[str, SSEClient] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._app = None
        self._server = None
    
    def _create_app(self):
        """Create the ASGI application."""
        try:
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse, StreamingResponse
            from starlette.routing import Route
            from starlette.middleware.cors import CORSMiddleware
        except ImportError:
            logger.warning("Starlette not installed. Server features unavailable.")
            return None
        
        async def health(request):
            return JSONResponse({
                "status": "ok",
                "timestamp": time.time(),
                "clients": len(self._clients),
            })
        
        async def events(request):
            client_id = str(uuid.uuid4())
            client = SSEClient(client_id)
            self._clients[client_id] = client
            
            logger.info(f"SSE client connected: {client_id}")
            
            async def event_generator():
                try:
                    for event in client.events():
                        yield event
                finally:
                    client.disconnect()
                    self._clients.pop(client_id, None)
                    logger.info(f"SSE client disconnected: {client_id}")
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        
        async def publish(request):
            try:
                data = await request.json()
                event_type = data.get("type", "message")
                event_data = data.get("data", {})
                
                self.broadcast(event_type, event_data)
                
                return JSONResponse({
                    "success": True,
                    "clients": len(self._clients),
                })
            except Exception as e:
                return JSONResponse(
                    {"success": False, "error": str(e)},
                    status_code=400
                )
        
        async def info(request):
            return JSONResponse({
                "name": "PraisonAI Agent Server",
                "version": "1.0.0",
                "clients": len(self._clients),
                "config": self.config.to_dict(),
            })
        
        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/events", events, methods=["GET"]),
            Route("/publish", publish, methods=["POST"]),
            Route("/info", info, methods=["GET"]),
        ]
        
        app = Starlette(routes=routes)
        
        # Add CORS middleware
        app = CORSMiddleware(
            app,
            allow_origins=self.config.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        return app
    
    def broadcast(self, event_type: str, data: Dict[str, Any]):
        """
        Broadcast an event to all connected clients.
        
        Args:
            event_type: The event type
            data: The event data
        """
        for client in list(self._clients.values()):
            try:
                client.send(event_type, data)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
    
    def on_event(self, event_type: str) -> Callable:
        """
        Decorator to register an event handler.
        
        Args:
            event_type: The event type to handle
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func
        return decorator
    
    def start(self, blocking: bool = False):
        """
        Start the server.
        
        Args:
            blocking: If True, block until server stops
        """
        if self._running:
            logger.warning("Server already running")
            return
        
        self._app = self._create_app()
        if self._app is None:
            logger.error("Failed to create app - missing dependencies")
            return
        
        self._running = True
        
        if blocking:
            self._run_server()
        else:
            self._server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self._server_thread.start()
            # Give server time to start
            time.sleep(0.5)
        
        logger.info(f"Server started on {self.host}:{self.port}")
    
    def _run_server(self):
        """Run the server in an event loop."""
        try:
            import uvicorn
            
            config = uvicorn.Config(
                self._app,
                host=self.host,
                port=self.port,
                log_level="warning",
            )
            self._server = uvicorn.Server(config)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._server.serve())
        except ImportError:
            logger.error("uvicorn not installed. Cannot start server.")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self._running = False
    
    def stop(self):
        """Stop the server."""
        if not self._running:
            return
        
        self._running = False
        
        # Disconnect all clients
        for client in list(self._clients.values()):
            client.disconnect()
        self._clients.clear()
        
        # Stop the server
        if self._server:
            self._server.should_exit = True
        
        logger.info("Server stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
