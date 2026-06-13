"""Runtime Registry.

Plugin registry for runtime implementations following AGENTS.md patterns:
- Thread-safe registration with factory pattern
- Built-in runtime support
- Entry points discovery for plugin runtimes
- Minimal dependencies (no heavy imports at module level)
"""

import threading
from typing import Dict, Callable, Any, Optional
from .protocols import AgentRuntimeProtocol

# For now, we'll implement a simple registry until we can import the canonical PluginRegistry
# TODO: Refactor to use canonical PluginRegistry from wrapper layer

# Global runtime registry state
_runtimes: Dict[str, Callable[[], AgentRuntimeProtocol]] = {}
_runtime_aliases: Dict[str, str] = {}
_registry_lock = threading.RLock()


def _get_builtin_runtime_factories() -> Dict[str, Callable[[], Callable[[], AgentRuntimeProtocol]]]:
    """Get built-in runtime factory loaders."""
    def praisonai_loader():
        def factory():
            from .builtin import PraisonAIRuntime
            return PraisonAIRuntime()
        return factory
    
    return {
        "praisonai": praisonai_loader
    }


def _initialize_builtin_runtimes() -> None:
    """Initialize built-in runtimes if not already done."""
    builtin_factories = _get_builtin_runtime_factories()
    
    with _registry_lock:
        for runtime_id, loader in builtin_factories.items():
            if runtime_id not in _runtimes:
                _runtimes[runtime_id] = loader()


def register_runtime(runtime_id: str, factory: Callable[[], AgentRuntimeProtocol]) -> None:
    """Register a runtime factory.
    
    Args:
        runtime_id: Unique identifier (e.g., "praisonai", "claude-code") 
        factory: Factory function that returns an AgentRuntimeProtocol instance
    """
    with _registry_lock:
        _runtimes[runtime_id] = factory


def unregister_runtime(runtime_id: str) -> bool:
    """Unregister a runtime.
    
    Args:
        runtime_id: Runtime identifier
        
    Returns:
        True if runtime was found and removed, False otherwise
    """
    with _registry_lock:
        if runtime_id in _runtimes:
            del _runtimes[runtime_id]
            # Remove any aliases pointing to this runtime
            aliases_to_remove = [
                alias for alias, canonical in _runtime_aliases.items()
                if canonical == runtime_id
            ]
            for alias in aliases_to_remove:
                del _runtime_aliases[alias]
            return True
        return False


def list_runtimes() -> list[str]:
    """List all registered runtime IDs."""
    _initialize_builtin_runtimes()
    with _registry_lock:
        return sorted(_runtimes.keys())


def resolve_runtime(runtime_id: str) -> AgentRuntimeProtocol:
    """Resolve a runtime by ID.
    
    Args:
        runtime_id: Runtime identifier (e.g., "praisonai")
        
    Returns:
        AgentRuntimeProtocol instance
        
    Raises:
        ValueError: If runtime_id is not registered
    """
    _initialize_builtin_runtimes()
    
    with _registry_lock:
        # Check for alias
        canonical_id = _runtime_aliases.get(runtime_id, runtime_id)
        
        if canonical_id not in _runtimes:
            available = sorted(_runtimes.keys())
            raise ValueError(f"Unknown runtime: {runtime_id}. Available: {available}")
        
        factory = _runtimes[canonical_id]
    
    # Create instance outside of lock to prevent deadlock
    return factory()


def add_runtime_alias(alias: str, canonical_runtime_id: str) -> None:
    """Add an alias for a runtime.
    
    Args:
        alias: Alias name
        canonical_runtime_id: The canonical runtime ID this alias points to
        
    Raises:
        ValueError: If canonical runtime ID is not registered
    """
    _initialize_builtin_runtimes()
    
    with _registry_lock:
        if canonical_runtime_id not in _runtimes:
            available = sorted(_runtimes.keys())
            raise ValueError(f"Cannot create alias '{alias}' for unknown runtime: {canonical_runtime_id}. Available: {available}")
        
        _runtime_aliases[alias] = canonical_runtime_id


def is_runtime_available(runtime_id: str) -> bool:
    """Check if a runtime is available.
    
    Args:
        runtime_id: Runtime identifier
        
    Returns:
        True if runtime exists and can be created
    """
    try:
        resolve_runtime(runtime_id)
        return True
    except ValueError:
        return False


class RuntimeRegistry:
    """Runtime registry class for dependency injection scenarios.
    
    This provides the same interface as the functional API above
    but as a class for cases where dependency injection is preferred.
    """
    
    def __init__(self):
        """Initialize runtime registry."""
        # Use the global registry state for simplicity
        # In a more complex setup, this could have its own state
        pass
    
    def register(self, runtime_id: str, factory: Callable[[], AgentRuntimeProtocol]) -> None:
        """Register a runtime factory."""
        register_runtime(runtime_id, factory)
    
    def unregister(self, runtime_id: str) -> bool:
        """Unregister a runtime."""
        return unregister_runtime(runtime_id)
    
    def list_names(self) -> list[str]:
        """List all registered runtime names."""
        return list_runtimes()
    
    def resolve(self, runtime_id: str) -> AgentRuntimeProtocol:
        """Resolve a runtime by ID."""
        return resolve_runtime(runtime_id)
    
    def is_available(self, runtime_id: str) -> bool:
        """Check if a runtime is available."""
        return is_runtime_available(runtime_id)
    
    def add_alias(self, alias: str, canonical_runtime_id: str) -> None:
        """Add an alias for a runtime."""
        add_runtime_alias(alias, canonical_runtime_id)


# Auto-discovery of entry points
def _discover_entry_point_runtimes() -> None:
    """Discover runtimes from entry points."""
    try:
        from importlib.metadata import entry_points
        
        for ep in entry_points(group="praisonai.runtimes"):
            def make_loader(entry_point):
                def loader():
                    factory_class = entry_point.load()
                    return factory_class()
                return loader
            
            with _registry_lock:
                if ep.name not in _runtimes:
                    _runtimes[ep.name] = make_loader(ep)
                    
    except ImportError:
        # entry_points not available in older Python versions
        pass
    except Exception:
        # Ignore discovery errors - plugins are optional
        pass


# Initialize on module load
_discover_entry_point_runtimes()