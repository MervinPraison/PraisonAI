"""Runtime registry for PraisonAI Agents.

Protocol-driven design following AGENTS.md:
- Core protocols only (no heavy implementations)
- Registry pattern for runtime resolution
- Support for both TurnRuntime and AgentRuntime patterns
"""

import threading
from typing import Protocol, Dict, Any, Optional, List, runtime_checkable, Callable
from dataclasses import dataclass
import logging

try:
    from importlib.metadata import entry_points
    def iter_entry_points(group):
        try:
            # Python 3.10+ supports group parameter
            return entry_points(group=group)
        except TypeError:
            # Python 3.8/3.9 fallback - entry_points() returns a dict
            eps = entry_points()
            return eps.get(group, [])
except ImportError:
    try:
        from pkg_resources import iter_entry_points
    except ImportError:
        def iter_entry_points(group):
            return []

logger = logging.getLogger(__name__)


@dataclass
class RuntimeRegistryEntry:
    """Entry in the runtime registry containing runtime metadata."""
    runtime_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_builtin: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.display_name is None:
            self.display_name = self.runtime_id


@runtime_checkable
class RuntimeRegistry(Protocol):
    """Protocol for runtime registries.
    
    Defines the interface for registering and resolving agent runtimes.
    The actual implementation lives in the wrapper layer.
    """
    
    def register(self, runtime_id: str, factory_or_instance: Any, **metadata) -> None:
        """Register a runtime with the registry.
        
        Args:
            runtime_id: Unique runtime identifier (e.g., "claude-code")
            factory_or_instance: Runtime factory function or instance
            **metadata: Additional metadata for the runtime
        
        Raises:
            ValueError: If runtime_id is already registered
            TypeError: If factory_or_instance is not callable or valid instance
        """
        ...
    
    def unregister(self, runtime_id: str) -> bool:
        """Unregister a runtime from the registry.
        
        Args:
            runtime_id: Runtime identifier to unregister
            
        Returns:
            True if runtime was unregistered, False if not found
        """
        ...
    
    def is_registered(self, runtime_id: str) -> bool:
        """Check if a runtime is registered.
        
        Args:
            runtime_id: Runtime identifier to check
            
        Returns:
            True if runtime is registered, False otherwise
        """
        ...
    
    def list_runtimes(self) -> List[RuntimeRegistryEntry]:
        """List all registered runtimes.
        
        Returns:
            List of RuntimeRegistryEntry objects for all registered runtimes
        """
        ...
    
    def get_entry(self, runtime_id: str) -> Optional[RuntimeRegistryEntry]:
        """Get registry entry for a runtime.
        
        Args:
            runtime_id: Runtime identifier
            
        Returns:
            RuntimeRegistryEntry if found, None otherwise
        """
        ...
    
    def resolve(self, runtime_id: str, config_overrides: Optional[Dict[str, Any]] = None) -> Any:
        """Resolve a runtime by ID with optional configuration overrides.
        
        Args:
            runtime_id: Runtime identifier to resolve
            config_overrides: Optional configuration overrides
            
        Returns:
            Runtime instance (typically implementing CliBackendProtocol)
            
        Raises:
            ValueError: If runtime_id is not registered (fail-closed behavior)
            TypeError: If runtime cannot be instantiated
        """
        ...
    
    def clear(self) -> None:
        """Clear all registered runtimes.
        
        Used primarily for testing and cleanup.
        """
        ...


# Global registry instance - will be initialized by wrapper layer
_global_registry: Optional[RuntimeRegistry] = None
_registry_lock = threading.Lock()


def set_global_registry(registry: RuntimeRegistry) -> None:
    """Set the global runtime registry instance.
    
    This is called by the wrapper layer to inject the actual registry implementation.
    
    Args:
        registry: RuntimeRegistry implementation
        
    Raises:
        TypeError: If registry doesn't implement RuntimeRegistry protocol
    """
    global _global_registry
    
    if not isinstance(registry, RuntimeRegistry):
        raise TypeError("registry must implement RuntimeRegistry protocol")
    
    with _registry_lock:
        _global_registry = registry


def get_global_registry() -> Optional[RuntimeRegistry]:
    """Get the global runtime registry instance.
    
    Returns:
        RuntimeRegistry instance if set, None otherwise
    """
    with _registry_lock:
        return _global_registry


def list_available_runtimes() -> List[RuntimeRegistryEntry]:
    """List all available runtimes from the global registry.
    
    Returns:
        List of RuntimeRegistryEntry objects, empty list if registry not initialized
    """
    registry = get_global_registry()
    if registry is None:
        return []
    
    return registry.list_runtimes()


def is_runtime_available(runtime_id: str) -> bool:
    """Check if a runtime is available in the global registry.
    
    Args:
        runtime_id: Runtime identifier to check
        
    Returns:
        True if runtime is available, False otherwise
    """
    registry = get_global_registry()
    if registry is None:
        return False
    
    return registry.is_registered(runtime_id)


# ==============================================================================
# Agent Runtime Registry (for auto-selection feature)
# ==============================================================================

class SimpleRuntimeRegistry:
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
                # Wrap in lazy factory to defer module loading until runtime is resolved
                def make_lazy_factory(ep):
                    def lazy_factory():
                        loaded = ep.load()  # Load module on demand
                        return loaded()  # Call factory to create runtime instance
                    return lazy_factory
                self._factories[entry_point.name] = make_lazy_factory(entry_point)
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


# Global runtime registry instance for agent runtime selection
_agent_runtime_registry: Optional[SimpleRuntimeRegistry] = None
_agent_registry_lock = threading.Lock()


def _get_agent_runtime_registry() -> SimpleRuntimeRegistry:
    """Get the runtime registry instance."""
    global _agent_runtime_registry
    if _agent_runtime_registry is None:
        with _agent_registry_lock:
            if _agent_runtime_registry is None:
                _agent_runtime_registry = SimpleRuntimeRegistry(
                    entry_point_group="praisonai.runtimes",
                    builtins=_get_builtin_runtime_loaders()
                )
    return _agent_runtime_registry


def register_runtime(runtime_id: str, factory: Callable[[], Any]) -> None:
    """Register a runtime factory.
    
    Args:
        runtime_id: Unique identifier (e.g., "praisonai", "modal", "e2b")
        factory: Factory function that returns an AgentRuntimeProtocol instance
    """
    def factory_loader():
        return factory
    
    registry = _get_agent_runtime_registry()
    registry.register(runtime_id, factory_loader)


def list_runtimes() -> List[str]:
    """List all registered runtime IDs."""
    registry = _get_agent_runtime_registry()
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
    registry = _get_agent_runtime_registry()
    return registry.resolve(runtime_id)


def get_all_runtime_factories() -> Dict[str, Callable[[], Any]]:
    """Get all registered runtime factories.
    
    Returns:
        Dict mapping runtime_id to factory function
    """
    registry = _get_agent_runtime_registry()
    factories = {}
    
    for runtime_id in registry.list_names():
        try:
            factory = registry.resolve(runtime_id)
            factories[runtime_id] = factory
        except Exception as e:
            # Skip runtimes that fail to load
            logger.debug(f"Skipping runtime '{runtime_id}' that failed to resolve: {e}")
            continue
            
    return factories