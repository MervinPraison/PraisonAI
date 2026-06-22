"""
Middleware Registry for managing runtime-scoped tool result middleware.

Provides a global registry where plugin harnesses can register their
middleware implementations and the core tool execution system can
look up the appropriate middleware for a given runtime.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional
from threading import RLock

from .middleware import RuntimeToolResultMiddleware, PassThroughMiddleware, MiddlewareContext, NormalizedToolResult

logger = logging.getLogger(__name__)


class MiddlewareRegistry:
    """Registry for runtime-scoped tool result middleware.
    
    Thread-safe singleton-like registry that manages middleware instances
    for different runtime environments. Plugin harnesses register their
    middleware here, and the core tool execution system uses it to normalize
    results before they reach hooks and memory adapters.
    
    Example:
        # In plugin harness initialization
        registry = MiddlewareRegistry()
        registry.register("claude_harness", ClaudeHarnessMiddleware())
        
        # In core tool execution (agent.execute_tool)
        registry = MiddlewareRegistry()
        middleware = registry.get_middleware("claude_harness")
        normalized = middleware.normalize(result, tool_name, ctx)
    """
    
    def __init__(self):
        self._middleware: Dict[str, RuntimeToolResultMiddleware] = {}
        self._lock = RLock()
        self._default_middleware = PassThroughMiddleware()
    
    def register(self, runtime_id: str, middleware: RuntimeToolResultMiddleware) -> None:
        """Register middleware for a specific runtime.
        
        Args:
            runtime_id: Unique identifier for the runtime (e.g., "claude_harness")
            middleware: Middleware instance implementing RuntimeToolResultMiddleware
        """
        with self._lock:
            if runtime_id in self._middleware:
                logger.warning(f"Replacing existing middleware for runtime '{runtime_id}'")
            
            self._middleware[runtime_id] = middleware
            logger.debug(f"Registered middleware for runtime '{runtime_id}': {type(middleware).__name__}")
    
    def unregister(self, runtime_id: str) -> bool:
        """Unregister middleware for a runtime.
        
        Args:
            runtime_id: Runtime identifier to unregister
            
        Returns:
            True if middleware was found and removed, False otherwise
        """
        with self._lock:
            if runtime_id in self._middleware:
                del self._middleware[runtime_id]
                logger.debug(f"Unregistered middleware for runtime '{runtime_id}'")
                return True
            return False
    
    def get_middleware(self, runtime_id: str) -> RuntimeToolResultMiddleware:
        """Get middleware for a runtime.
        
        Args:
            runtime_id: Runtime identifier to look up
            
        Returns:
            Registered middleware or default pass-through middleware
        """
        with self._lock:
            middleware = self._middleware.get(runtime_id)
            if middleware is not None:
                return middleware
            
            # Return pass-through middleware for unregistered runtimes
            # This avoids allocation overhead for native 'praisonai' runtime
            return self._default_middleware
    
    def has_middleware(self, runtime_id: str) -> bool:
        """Check if middleware is registered for a runtime.
        
        Args:
            runtime_id: Runtime identifier to check
            
        Returns:
            True if custom middleware is registered, False otherwise
        """
        with self._lock:
            return runtime_id in self._middleware
    
    def list_runtimes(self) -> list[str]:
        """List all registered runtime IDs.
        
        Returns:
            List of runtime IDs with registered middleware
        """
        with self._lock:
            return list(self._middleware.keys())
    
    def clear(self) -> None:
        """Clear all registered middleware.
        
        Useful for testing and cleanup scenarios.
        """
        with self._lock:
            self._middleware.clear()
            logger.debug("Cleared all runtime middleware registrations")


# Global registry instance
_global_middleware_registry: Optional[MiddlewareRegistry] = None
_middleware_registry_lock = RLock()


def get_default_middleware_registry() -> MiddlewareRegistry:
    """Get the global default middleware registry.
    
    Implements thread-safe singleton pattern for the global registry.
    
    Returns:
        Global MiddlewareRegistry instance
    """
    global _global_middleware_registry
    
    if _global_middleware_registry is not None:
        return _global_middleware_registry
    
    with _middleware_registry_lock:
        if _global_middleware_registry is None:
            _global_middleware_registry = MiddlewareRegistry()
        return _global_middleware_registry


def register_middleware(runtime_id: str, middleware: RuntimeToolResultMiddleware) -> None:
    """Register middleware in the global registry.
    
    Convenience function for plugin harnesses to register their middleware.
    
    Args:
        runtime_id: Unique identifier for the runtime
        middleware: Middleware instance
    """
    registry = get_default_middleware_registry()
    registry.register(runtime_id, middleware)


def get_middleware(runtime_id: str) -> RuntimeToolResultMiddleware:
    """Get middleware from the global registry.
    
    Convenience function for core tool execution to get middleware.
    
    Args:
        runtime_id: Runtime identifier
        
    Returns:
        Registered middleware or default pass-through middleware
    """
    registry = get_default_middleware_registry()
    return registry.get_middleware(runtime_id)