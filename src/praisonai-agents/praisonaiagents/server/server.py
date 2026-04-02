"""
Lightweight server adapter for protocol-driven architecture.

This replaces the heavy server implementation which has been moved to the wrapper package.
Now contains only lightweight protocol adapters that delegate to the wrapper implementation.

ARCHITECTURAL CHANGE:
- Removed: 330+ lines of HTTP server, SSE, queues, threading implementation
- Added: Lightweight protocol adapter that delegates to wrapper package
"""

import json
import queue
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional
import logging

# Use centralized lazy loading
from .._lazy import lazy_import

logger = logging.getLogger(__name__)

# Default configuration  
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SSE_KEEPALIVE_TIMEOUT = 30  # seconds between keepalive pings


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
                event = self.queue.get(timeout=SSE_KEEPALIVE_TIMEOUT)
                yield f"id: {event['id']}\n"
                yield f"event: {event['event']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"

class AgentServer:
    """
    Lightweight server adapter that delegates to wrapper implementation.
    
    This maintains backward compatibility while following protocol-driven architecture.
    The actual heavy implementation (HTTP, SSE, queues, threading) is in the wrapper package.
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        config: Optional[Any] = None,
    ):
        """Initialize lightweight server adapter.

        *config* may be a :class:`ServerConfig` instance; when supplied it
        takes precedence over *host* and *port* positional arguments.
        """
        if isinstance(config, ServerConfig):
            self._host = config.host
            self._port = config.port
        else:
            self._host = host
            self._port = port
        self._config = config
        self._clients: Dict[str, SSEClient] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._wrapper_server = None

    @property
    def host(self) -> str:
        """Server host."""
        return self._host

    @property
    def port(self) -> int:
        """Server port."""
        return self._port
    
    def _get_wrapper_server(self):
        """Lazy load the wrapper server implementation."""
        if self._wrapper_server is None:
            try:
                # Lazy import from wrapper package
                WrapperServer = lazy_import('praisonai.server', 'AgentServer')
                self._wrapper_server = WrapperServer(self._host, self._port, self._config)
            except (ImportError, AttributeError):
                # Fallback to minimal implementation
                logger.warning("Wrapper server not available, using minimal fallback")
                self._wrapper_server = _MinimalServer(self._host, self._port)
        return self._wrapper_server
    
    def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        for client in list(self._clients.values()):
            if client.connected:
                client.send(event_type, data)
    
    def on_event(self, event_type: str) -> Callable:
        """Decorator to register an event handler."""
        def decorator(func: Callable) -> Callable:
            self._event_handlers.setdefault(event_type, []).append(func)
            return func
        return decorator
    
    def start(self, blocking: bool = False):
        """Start the server."""
        self._running = True
        self._get_wrapper_server().start(blocking)
    
    def stop(self):
        """Stop the server."""
        self._running = False
        for client in list(self._clients.values()):
            client.disconnect()
        if self._wrapper_server:
            self._wrapper_server.stop()
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len([c for c in self._clients.values() if c.connected])
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class _MinimalServer:
    """Minimal fallback when wrapper is not available."""
    
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._running = False
        self._event_handlers = {}
    
    def broadcast(self, event_type: str, data: Dict[str, Any]):
        logger.debug(f"Minimal server broadcast: {event_type}")
    
    def on_event(self, event_type: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func
        return decorator
    
    def start(self, blocking: bool = False):
        logger.info(f"Minimal server started (mock) on {self._host}:{self._port}")
        self._running = True
    
    def stop(self):
        logger.info("Minimal server stopped")
        self._running = False
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def client_count(self) -> int:
        return 0


# Backward compatibility alias
Server = AgentServer