"""
Lightweight server adapter for protocol-driven architecture.

This replaces the heavy server implementation which has been moved to the wrapper package.
Now contains only lightweight protocol adapters that delegate to the wrapper implementation.

ARCHITECTURAL CHANGE:
- Removed: 330+ lines of HTTP server, SSE, queues, threading implementation
- Added: Lightweight protocol adapter that delegates to wrapper package
"""

from typing import Any, Callable, Dict, Optional
import logging

# Use centralized lazy loading
from .._lazy import lazy_import

logger = logging.getLogger(__name__)

# Default configuration  
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

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
        """Initialize lightweight server adapter."""
        self._host = host
        self._port = port
        self._config = config
        self._wrapper_server = None
    
    def _get_wrapper_server(self):
        """Lazy load the wrapper server implementation."""
        if self._wrapper_server is None:
            try:
                # Lazy import from wrapper package
                WrapperServer = lazy_import('praisonai.server', 'AgentServer')
                self._wrapper_server = WrapperServer(self._host, self._port, self._config)
            except ImportError:
                # Fallback to minimal implementation
                logger.warning("Wrapper server not available, using minimal fallback")
                self._wrapper_server = _MinimalServer(self._host, self._port)
        return self._wrapper_server
    
    # Delegate all methods to wrapper implementation
    def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        self._get_wrapper_server().broadcast(event_type, data)
    
    def on_event(self, event_type: str) -> Callable:
        """Decorator to register an event handler."""
        return self._get_wrapper_server().on_event(event_type)
    
    def start(self, blocking: bool = False):
        """Start the server."""
        self._get_wrapper_server().start(blocking)
    
    def stop(self):
        """Stop the server."""
        if self._wrapper_server:
            self._wrapper_server.stop()
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._get_wrapper_server().is_running
    
    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return self._get_wrapper_server().client_count
    
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