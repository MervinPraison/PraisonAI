"""Centralized server management for agents and multi-agent systems.

This module provides a singleton ServerManager class that handles all FastAPI
server creation, management, and endpoint registration across both the agent
and agents modules, eliminating code duplication and providing consistent
server handling.
"""

import logging
import threading
from typing import Dict, Any, Optional, Set

logger = logging.getLogger(__name__)


class ServerManager:
    """Manages shared FastAPI servers across agent and agents modules.
    
    This singleton class provides centralized management for:
    - FastAPI app creation and caching
    - Endpoint registration and conflict detection
    - Server startup state tracking
    - Thread-safe operations
    
    The manager ensures that only one FastAPI server runs per port,
    regardless of how many agents or agent systems are using it.
    """
    
    def __init__(self):
        """Initialize the server manager with thread-safe data structures."""
        self._lock = threading.Lock()
        self._servers: Dict[int, Dict[str, Any]] = {}
        # Structure: {port: {'app': FastAPI, 'started': bool, 'endpoints': set(), 'thread': Thread}}
    
    def get_or_create_app(self, port: int = 8000, title: Optional[str] = None):
        """Get existing app or create new one for the specified port.
        
        Args:
            port: Port number for the server
            title: Optional title for the FastAPI app
            
        Returns:
            FastAPI application instance
        """
        with self._lock:
            if port not in self._servers:
                # Lazy import to avoid circular dependencies
                from fastapi import FastAPI
                
                app_title = title or f"PraisonAI Agents API - Port {port}"
                app = FastAPI(title=app_title)
                
                self._servers[port] = {
                    'app': app,
                    'started': False,
                    'endpoints': set(),
                    'thread': None
                }
                
                logger.info(f"Created new FastAPI app for port {port}")
            
            return self._servers[port]['app']
    
    def register_endpoint(self, port: int, path: str, endpoint_id: str) -> bool:
        """Register an endpoint to avoid duplicates.
        
        Args:
            port: Port number
            path: API endpoint path
            endpoint_id: Unique identifier for the endpoint
            
        Returns:
            True if registration successful, False if endpoint already exists
        """
        with self._lock:
            if port not in self._servers:
                self.get_or_create_app(port)
            
            endpoints = self._servers[port]['endpoints']
            
            # Check if this exact path is already registered
            if path in endpoints:
                logger.warning(f"Endpoint {path} already registered on port {port}")
                return False
            
            endpoints.add(path)
            logger.debug(f"Registered endpoint {path} (ID: {endpoint_id}) on port {port}")
            return True
    
    def unregister_endpoint(self, port: int, path: str):
        """Unregister an endpoint.
        
        Args:
            port: Port number
            path: API endpoint path
        """
        with self._lock:
            if port in self._servers and path in self._servers[port]['endpoints']:
                self._servers[port]['endpoints'].remove(path)
                logger.debug(f"Unregistered endpoint {path} from port {port}")
    
    def is_endpoint_registered(self, port: int, path: str) -> bool:
        """Check if an endpoint is already registered.
        
        Args:
            port: Port number
            path: API endpoint path
            
        Returns:
            True if endpoint is registered, False otherwise
        """
        with self._lock:
            return port in self._servers and path in self._servers[port]['endpoints']
    
    def get_registered_endpoints(self, port: int) -> Set[str]:
        """Get all registered endpoints for a port.
        
        Args:
            port: Port number
            
        Returns:
            Set of registered endpoint paths
        """
        with self._lock:
            if port in self._servers:
                return self._servers[port]['endpoints'].copy()
            return set()
    
    def mark_started(self, port: int, thread: Optional[threading.Thread] = None):
        """Mark server as started.
        
        Args:
            port: Port number
            thread: Optional thread running the server
        """
        with self._lock:
            if port in self._servers:
                self._servers[port]['started'] = True
                if thread:
                    self._servers[port]['thread'] = thread
                logger.info(f"Server on port {port} marked as started")
    
    def is_started(self, port: int) -> bool:
        """Check if server is started.
        
        Args:
            port: Port number
            
        Returns:
            True if server is started, False otherwise
        """
        with self._lock:
            return port in self._servers and self._servers[port]['started']
    
    def get_server_thread(self, port: int) -> Optional[threading.Thread]:
        """Get the thread running the server.
        
        Args:
            port: Port number
            
        Returns:
            Thread instance if server is running, None otherwise
        """
        with self._lock:
            if port in self._servers:
                return self._servers[port].get('thread')
            return None
    
    def get_all_servers(self) -> Dict[int, Dict[str, Any]]:
        """Get information about all managed servers.
        
        Returns:
            Dictionary mapping ports to server information
        """
        with self._lock:
            return {
                port: {
                    'started': info['started'],
                    'endpoints': list(info['endpoints']),
                    'has_thread': info['thread'] is not None
                }
                for port, info in self._servers.items()
            }
    
    def cleanup_port(self, port: int):
        """Clean up server resources for a specific port.
        
        Args:
            port: Port number to clean up
        """
        with self._lock:
            if port in self._servers:
                del self._servers[port]
                logger.info(f"Cleaned up server resources for port {port}")
    
    def reset(self):
        """Reset the server manager, clearing all server data.
        
        This is mainly useful for testing.
        """
        with self._lock:
            self._servers.clear()
            logger.info("Server manager reset - all server data cleared")


# Global singleton instance
server_manager = ServerManager()


# Convenience functions for backward compatibility
def get_shared_app(port: int = 8000):
    """Get or create a shared FastAPI app for the given port.
    
    Args:
        port: Port number
        
    Returns:
        FastAPI application instance
    """
    return server_manager.get_or_create_app(port)


def is_server_started(port: int = 8000) -> bool:
    """Check if the server on the given port is started.
    
    Args:
        port: Port number
        
    Returns:
        True if server is started, False otherwise
    """
    return server_manager.is_started(port)


def mark_server_started(port: int = 8000, thread: Optional[threading.Thread] = None):
    """Mark the server on the given port as started.
    
    Args:
        port: Port number
        thread: Optional thread running the server
    """
    server_manager.mark_started(port, thread)


__all__ = [
    'ServerManager',
    'server_manager',
    'get_shared_app',
    'is_server_started',
    'mark_server_started',
]