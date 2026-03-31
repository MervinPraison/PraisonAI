"""
Unified thread-safe server registry for managing API server state.

This module replaces the duplicate server state management found in:
- agent/agent.py (_server_started, _registered_agents, _shared_apps)
- agents/agents.py (_agents_server_started, _agents_registered_endpoints, _agents_shared_apps)

Design follows AGENTS.md principle of "Multi-agent + async safe by default".
"""

import threading
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field


@dataclass
class ServerInfo:
    """Information about a registered server instance."""
    port: int
    started: bool = False
    app: Optional[Any] = None  # FastAPI app instance
    endpoints: Dict[str, str] = field(default_factory=dict)  # path -> agent/endpoint_id
    agents: Dict[str, str] = field(default_factory=dict)  # path -> agent_id (for backward compatibility)


class ServerRegistry:
    """
    Thread-safe singleton registry for managing API server state.
    
    Replaces duplicate lock domains in agent.py and agents.py with a unified,
    thread-safe approach that prevents port conflicts and race conditions.
    """
    
    _instance = None
    _creation_lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern with thread-safe creation."""
        if cls._instance is None:
            with cls._creation_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the registry (only once due to singleton pattern)."""
        if not getattr(self, '_initialized', False):
            self._lock = threading.Lock()
            self._servers: Dict[int, ServerInfo] = {}
            self._initialized = True
    
    def register_server(self, port: int, app: Any = None) -> ServerInfo:
        """
        Register a server on the given port.
        
        Args:
            port: Port number for the server
            app: Optional FastAPI app instance
            
        Returns:
            ServerInfo object for the registered server
            
        Raises:
            ValueError: If port is already registered with a different app
        """
        with self._lock:
            if port in self._servers:
                server_info = self._servers[port]
                if app is not None and server_info.app is not None and server_info.app is not app:
                    raise ValueError(f"Port {port} already registered with different app")
                # Update app if provided
                if app is not None:
                    server_info.app = app
                return server_info
            
            # Create new server info
            server_info = ServerInfo(port=port, app=app)
            self._servers[port] = server_info
            return server_info
    
    def mark_started(self, port: int) -> None:
        """Mark a server as started."""
        with self._lock:
            if port in self._servers:
                self._servers[port].started = True
    
    def mark_stopped(self, port: int) -> None:
        """Mark a server as stopped."""
        with self._lock:
            if port in self._servers:
                self._servers[port].started = False
    
    def is_started(self, port: int) -> bool:
        """Check if a server is started."""
        with self._lock:
            return self._servers.get(port, ServerInfo(port)).started
    
    def get_app(self, port: int) -> Optional[Any]:
        """Get the FastAPI app for a server."""
        with self._lock:
            return self._servers.get(port, ServerInfo(port)).app
    
    def register_endpoint(self, port: int, path: str, endpoint_id: str) -> None:
        """Register an endpoint on a server."""
        with self._lock:
            if port not in self._servers:
                self._servers[port] = ServerInfo(port)
            self._servers[port].endpoints[path] = endpoint_id
    
    def register_agent(self, port: int, path: str, agent_id: str) -> None:
        """Register an agent on a server (backward compatibility)."""
        with self._lock:
            if port not in self._servers:
                self._servers[port] = ServerInfo(port)
            self._servers[port].agents[path] = agent_id
            # Also register as endpoint for unified access
            self._servers[port].endpoints[path] = agent_id
    
    def get_endpoints(self, port: int) -> Dict[str, str]:
        """Get all endpoints for a server."""
        with self._lock:
            if port in self._servers:
                return self._servers[port].endpoints.copy()
            return {}
    
    def get_agents(self, port: int) -> Dict[str, str]:
        """Get all agents for a server (backward compatibility)."""
        with self._lock:
            if port in self._servers:
                return self._servers[port].agents.copy()
            return {}
    
    def unregister_server(self, port: int) -> None:
        """Unregister a server and all its endpoints."""
        with self._lock:
            if port in self._servers:
                del self._servers[port]
    
    def list_ports(self) -> Set[int]:
        """Get all registered port numbers."""
        with self._lock:
            return set(self._servers.keys())
    
    def get_server_info(self, port: int) -> Optional[ServerInfo]:
        """Get complete server information."""
        with self._lock:
            if port in self._servers:
                # Return a copy to prevent external mutation
                info = self._servers[port]
                return ServerInfo(
                    port=info.port,
                    started=info.started,
                    app=info.app,
                    endpoints=info.endpoints.copy(),
                    agents=info.agents.copy()
                )
            return None
    
    def clear(self) -> None:
        """Clear all registered servers (useful for testing)."""
        with self._lock:
            self._servers.clear()


# Global registry instance
_registry = ServerRegistry()


# Convenience functions for easy access
def get_server_registry() -> ServerRegistry:
    """Get the global server registry instance."""
    return _registry


def register_server(port: int, app: Any = None) -> ServerInfo:
    """Register a server on the given port."""
    return _registry.register_server(port, app)


def is_server_started(port: int) -> bool:
    """Check if a server is started."""
    return _registry.is_started(port)


def mark_server_started(port: int) -> None:
    """Mark a server as started."""
    _registry.mark_started(port)


def mark_server_stopped(port: int) -> None:
    """Mark a server as stopped."""
    _registry.mark_stopped(port)


def get_server_app(port: int) -> Optional[Any]:
    """Get the FastAPI app for a server."""
    return _registry.get_app(port)


def register_agent_endpoint(port: int, path: str, agent_id: str) -> None:
    """Register an agent endpoint on a server."""
    _registry.register_agent(port, path, agent_id)


def register_endpoint(port: int, path: str, endpoint_id: str) -> None:
    """Register a generic endpoint on a server."""
    _registry.register_endpoint(port, path, endpoint_id)