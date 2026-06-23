"""Runtime registry for PraisonAI Agents.

This module provides both protocol-based registry interface (from main) and
a concrete implementation (from this branch) for runtime registration and resolution.

Protocol-driven design following AGENTS.md:
- Core protocols only (no heavy implementations at module level)
- Thread-safe registration with factory pattern
- Built-in runtime support
- Entry points discovery for plugin runtimes
- Fail-closed behavior for unknown runtime IDs
"""

import threading
from typing import Protocol, Dict, Callable, Any, Optional, List, runtime_checkable
from dataclasses import dataclass
from .protocols import AgentRuntimeProtocol


# Registry entry dataclass from main
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


# Protocol definition from main
@runtime_checkable
class RuntimeRegistryProtocol(Protocol):
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
            Runtime instance (typically implementing AgentRuntimeProtocol)
            
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


# Global registry state from this branch
_runtimes: Dict[str, Callable[[], AgentRuntimeProtocol]] = {}
_runtime_aliases: Dict[str, str] = {}
_runtime_metadata: Dict[str, Dict[str, Any]] = {}
_registry_lock = threading.RLock()
_builtin_initialized = False


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
    global _builtin_initialized
    
    if _builtin_initialized:
        return
        
    builtin_factories = _get_builtin_runtime_factories()
    
    with _registry_lock:
        if not _builtin_initialized:
            for runtime_id, loader in builtin_factories.items():
                if runtime_id not in _runtimes:
                    _runtimes[runtime_id] = loader()
                    _runtime_metadata[runtime_id] = {"is_builtin": True}
            _builtin_initialized = True


# Concrete implementation that implements the protocol
class RuntimeRegistry:
    """Concrete runtime registry implementation.
    
    This provides both the RuntimeRegistryProtocol interface and additional
    helper methods for managing runtimes.
    """
    
    def register(self, runtime_id: str, factory_or_instance: Any, **metadata) -> None:
        """Register a runtime with the registry."""
        if not callable(factory_or_instance):
            # If it's an instance, wrap in a factory
            def factory():
                return factory_or_instance
            factory_func = factory
        else:
            factory_func = factory_or_instance
        
        with _registry_lock:
            if runtime_id in _runtimes:
                raise ValueError(f"Runtime '{runtime_id}' is already registered")
            _runtimes[runtime_id] = factory_func
            _runtime_metadata[runtime_id] = metadata
    
    def unregister(self, runtime_id: str) -> bool:
        """Unregister a runtime."""
        with _registry_lock:
            if runtime_id in _runtimes:
                del _runtimes[runtime_id]
                if runtime_id in _runtime_metadata:
                    del _runtime_metadata[runtime_id]
                # Remove any aliases pointing to this runtime
                aliases_to_remove = [
                    alias for alias, canonical in _runtime_aliases.items()
                    if canonical == runtime_id
                ]
                for alias in aliases_to_remove:
                    del _runtime_aliases[alias]
                return True
            return False
    
    def is_registered(self, runtime_id: str) -> bool:
        """Check if a runtime is registered."""
        _initialize_builtin_runtimes()
        with _registry_lock:
            canonical_id = _runtime_aliases.get(runtime_id, runtime_id)
            return canonical_id in _runtimes
    
    def list_names(self) -> List[str]:
        """List all registered runtime names (IDs).
        
        Returns:
            List of runtime IDs
        """
        _initialize_builtin_runtimes()
        with _registry_lock:
            return list(_runtimes.keys())
    
    def is_available(self, runtime_id: str) -> bool:
        """Check if a runtime is available (registered).
        
        This is an alias for is_registered() to match the test expectations.
        
        Args:
            runtime_id: Runtime identifier
            
        Returns:
            True if runtime is registered or aliased, False otherwise
        """
        return self.is_registered(runtime_id)
    
    def list_runtimes(self) -> List[RuntimeRegistryEntry]:
        """List all registered runtimes."""
        _initialize_builtin_runtimes()
        with _registry_lock:
            entries = []
            for runtime_id in _runtimes:
                metadata = _runtime_metadata.get(runtime_id, {})
                entries.append(RuntimeRegistryEntry(
                    runtime_id=runtime_id,
                    display_name=metadata.get("display_name"),
                    description=metadata.get("description"),
                    is_builtin=metadata.get("is_builtin", False),
                    metadata=metadata
                ))
            return entries
    
    def list_names(self) -> List[str]:
        """List all registered runtime names/IDs."""
        entries = self.list_runtimes()
        return [e.runtime_id for e in entries]
    
    def get_entry(self, runtime_id: str) -> Optional[RuntimeRegistryEntry]:
        """Get registry entry for a runtime."""
        _initialize_builtin_runtimes()
        with _registry_lock:
            canonical_id = _runtime_aliases.get(runtime_id, runtime_id)
            if canonical_id not in _runtimes:
                return None
            metadata = _runtime_metadata.get(canonical_id, {})
            return RuntimeRegistryEntry(
                runtime_id=canonical_id,
                display_name=metadata.get("display_name"),
                description=metadata.get("description"),
                is_builtin=metadata.get("is_builtin", False),
                metadata=metadata
            )
    
    def resolve(self, runtime_id: str, config_overrides: Optional[Dict[str, Any]] = None) -> Any:
        """Resolve a runtime by ID."""
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
    
    def clear(self) -> None:
        """Clear all registered runtimes."""
        global _builtin_initialized
        with _registry_lock:
            _runtimes.clear()
            _runtime_aliases.clear()
            _runtime_metadata.clear()
            _builtin_initialized = False
    
    def add_alias(self, alias: str, canonical_runtime_id: str) -> None:
        """Add an alias for a runtime."""
        _initialize_builtin_runtimes()
        
        with _registry_lock:
            if canonical_runtime_id not in _runtimes:
                available = sorted(_runtimes.keys())
                raise ValueError(f"Cannot create alias '{alias}' for unknown runtime: {canonical_runtime_id}. Available: {available}")
            
            _runtime_aliases[alias] = canonical_runtime_id
    
    def is_available(self, runtime_id: str) -> bool:
        """Check if a runtime is available."""
        try:
            self.resolve(runtime_id)
            return True
        except ValueError:
            return False


# Global registry instance
_global_registry = RuntimeRegistry()


# Convenience functions that use the global registry
def register_runtime(runtime_id: str, factory: Callable[[], AgentRuntimeProtocol], **metadata) -> None:
    """Register a runtime factory with the global registry.
    
    Args:
        runtime_id: Unique identifier (e.g., "praisonai", "claude-code") 
        factory: Factory function that returns an AgentRuntimeProtocol instance
        **metadata: Additional metadata for the runtime
    """
    _global_registry.register(runtime_id, factory, **metadata)


def unregister_runtime(runtime_id: str) -> bool:
    """Unregister a runtime from the global registry.
    
    Args:
        runtime_id: Runtime identifier
        
    Returns:
        True if runtime was found and removed, False otherwise
    """
    return _global_registry.unregister(runtime_id)


def list_runtimes() -> list[str]:
    """List all registered runtime IDs."""
    entries = _global_registry.list_runtimes()
    return [e.runtime_id for e in entries]


def resolve_runtime(runtime_id: str) -> AgentRuntimeProtocol:
    """Resolve a runtime by ID using the global registry.
    
    Args:
        runtime_id: Runtime identifier (e.g., "praisonai")
        
    Returns:
        AgentRuntimeProtocol instance
        
    Raises:
        ValueError: If runtime_id is not registered
    """
    return _global_registry.resolve(runtime_id)


def add_runtime_alias(alias: str, canonical_runtime_id: str) -> None:
    """Add an alias for a runtime.
    
    Args:
        alias: Alias name
        canonical_runtime_id: The canonical runtime ID this alias points to
        
    Raises:
        ValueError: If canonical runtime ID is not registered
    """
    _global_registry.add_alias(alias, canonical_runtime_id)


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
                    _runtime_metadata[ep.name] = {"entry_point": str(ep)}
                    
    except ImportError:
        # entry_points not available in older Python versions
        pass
    except Exception:
        # Ignore discovery errors - plugins are optional
        pass


# Initialize on module load
_discover_entry_point_runtimes()
