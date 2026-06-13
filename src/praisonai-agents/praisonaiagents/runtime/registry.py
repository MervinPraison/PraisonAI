"""
Runtime Registry for Agent Harness Management.

Thread-safe registry for runtime factories with entry point discovery,
following AGENTS.md plugin patterns and PluginRegistry interface.
"""

import threading
from typing import Dict, Callable, Any, Optional, List
import logging

try:
    from importlib.metadata import entry_points
    def iter_entry_points(group):
        return entry_points(group=group)
except ImportError:
    try:
        from pkg_resources import iter_entry_points
    except ImportError:
        def iter_entry_points(group):
            return []

logger = logging.getLogger(__name__)


class RuntimeRegistry:
    """Simple registry for runtime factories without heavy dependencies.
    
    Core SDK variant focused on runtime harness registration and discovery.
    Avoids importing wrapper-level PluginRegistry to maintain clean separation.
    """
    
    def __init__(self, entry_point_group: str, builtins: Optional[Dict[str, Callable[[], Any]]] = None):
        self._entry_point_group = entry_point_group
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.RLock()
        
        # Register builtins
        if builtins:
            for name, factory_loader in builtins.items():
                self._factories[name] = factory_loader()
        
        # Discover entry points
        self._discover_entry_points()
    
    def _discover_entry_points(self) -> None:
        """Discover runtime factories from entry points."""
        try:
            for entry_point in iter_entry_points(self._entry_point_group):
                factory_loader = entry_point.load
                factory = factory_loader()
                self._factories[entry_point.name] = factory
        except Exception as e:
            logger.debug(f"Entry points discovery failed for {self._entry_point_group}: {e}")
    
    def register(self, name: str, factory_loader: Callable[[], Any]) -> None:
        """Register a runtime factory loader."""
        with self._lock:
            self._factories[name] = factory_loader()
    
    def resolve(self, name: str) -> Callable[[], Any]:
        """Resolve runtime factory by name."""
        with self._lock:
            if name not in self._factories:
                available = list(self._factories.keys())
                raise ValueError(f"Unknown runtime: {name}. Available: {available}")
            return self._factories[name]
    
    def list_names(self) -> List[str]:
        """List all registered runtime names."""
        with self._lock:
            return list(self._factories.keys())


def _get_builtin_runtime_loaders() -> Dict[str, Callable[[], Any]]:
    """Get built-in runtime loaders."""
    def praisonai_loader():
        def factory():
            from .builtin import PraisonAIRuntime
            return PraisonAIRuntime()
        return factory
    
    return {
        "praisonai": praisonai_loader
    }


# Global runtime registry instance
_runtime_registry: Optional[RuntimeRegistry] = None
_registry_lock = threading.Lock()


def _get_runtime_registry() -> RuntimeRegistry:
    """Get the runtime registry instance."""
    global _runtime_registry
    if _runtime_registry is None:
        with _registry_lock:
            if _runtime_registry is None:
                _runtime_registry = RuntimeRegistry(
                    entry_point_group="praisonai.runtimes",
                    builtins=_get_builtin_runtime_loaders()
                )
    return _runtime_registry


def register_runtime(runtime_id: str, factory: Callable[[], Any]) -> None:
    """Register a runtime factory.
    
    Args:
        runtime_id: Unique identifier (e.g., "praisonai", "modal", "e2b")
        factory: Factory function that returns an AgentRuntimeProtocol instance
    """
    def factory_loader():
        return factory
    
    registry = _get_runtime_registry()
    registry.register(runtime_id, factory_loader)


def list_runtimes() -> List[str]:
    """List all registered runtime IDs."""
    registry = _get_runtime_registry()
    return registry.list_names()


def resolve_runtime_factory(runtime_id: str) -> Callable[[], Any]:
    """Resolve a runtime factory by ID.
    
    Args:
        runtime_id: Runtime identifier
        
    Returns:
        Factory function that creates AgentRuntimeProtocol instance
        
    Raises:
        ValueError: If runtime_id is not registered
    """
    registry = _get_runtime_registry()
    return registry.resolve(runtime_id)


def get_all_runtime_factories() -> Dict[str, Callable[[], Any]]:
    """Get all registered runtime factories.
    
    Returns:
        Dict mapping runtime_id to factory function
    """
    registry = _get_runtime_registry()
    factories = {}
    
    for runtime_id in registry.list_names():
        try:
            factory = registry.resolve(runtime_id)
            factories[runtime_id] = factory
        except Exception:
            # Skip runtimes that fail to load
            continue
            
    return factories