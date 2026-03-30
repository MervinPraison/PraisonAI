"""
Centralized server registry for thread-safe server state management.
Unified solution for both Agent and Agents classes to share server resources safely.
"""

import threading
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class ServerRegistry:
    """
    Thread-safe centralized registry for managing shared FastAPI servers.
    
    This singleton class manages server state across Agent and Agents classes
    to prevent port conflicts and ensure thread safety.
    """
    
    _instance: Optional['ServerRegistry'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'ServerRegistry':
        """Ensure singleton pattern for global server state."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Initialize the server registry (only once)."""
        if self._initialized:
            return
            
        self._server_lock = threading.Lock()
        self._server_started: Dict[int, bool] = {}  # port -> started boolean
        self._registered_endpoints: Dict[int, Dict[str, str]] = {}  # port -> {path: endpoint_id}
        self._shared_apps: Dict[int, Any] = {}  # port -> FastAPI app
        self._initialized = True
    
    def is_server_started(self, port: int) -> bool:
        """Check if server is started on given port (thread-safe)."""
        with self._server_lock:
            return self._server_started.get(port, False)
    
    def mark_server_started(self, port: int) -> None:
        """Mark server as started on given port (thread-safe)."""
        with self._server_lock:
            self._server_started[port] = True
    
    def get_registered_endpoints(self, port: int) -> Dict[str, str]:
        """Get registered endpoints for a port (thread-safe)."""
        with self._server_lock:
            return self._registered_endpoints.get(port, {}).copy()
    
    def register_endpoint(self, port: int, path: str, endpoint_id: str) -> bool:
        """
        Register an endpoint for a port (thread-safe).
        
        Returns:
            bool: True if registered successfully, False if path already exists
        """
        with self._server_lock:
            if port not in self._registered_endpoints:
                self._registered_endpoints[port] = {}
            
            if path in self._registered_endpoints[port]:
                logger.warning(f"Path '{path}' is already registered on port {port}")
                return False
            
            self._registered_endpoints[port][path] = endpoint_id
            return True
    
    def get_shared_app(self, port: int) -> Optional[Any]:
        """Get the shared FastAPI app for a port (thread-safe)."""
        with self._server_lock:
            return self._shared_apps.get(port)
    
    def set_shared_app(self, port: int, app: Any) -> None:
        """Set the shared FastAPI app for a port (thread-safe)."""
        with self._server_lock:
            self._shared_apps[port] = app
    
    def initialize_port(self, port: int) -> None:
        """Initialize collections for a port if needed (thread-safe)."""
        with self._server_lock:
            if port not in self._registered_endpoints:
                self._registered_endpoints[port] = {}
    
    def get_server_info(self, port: int) -> Dict[str, Any]:
        """Get complete server info for a port (thread-safe)."""
        with self._server_lock:
            return {
                'started': self._server_started.get(port, False),
                'endpoints': self._registered_endpoints.get(port, {}).copy(),
                'has_app': port in self._shared_apps
            }


# Global singleton instance
_registry = ServerRegistry()

def get_server_registry() -> ServerRegistry:
    """Get the global server registry instance."""
    return _registry