"""Runtime registry protocol for PraisonAI Agents.

Protocol-driven design following AGENTS.md:
- Core protocols only (no heavy implementations)
- Registry pattern for runtime resolution
- Fail-closed behavior for unknown runtime IDs
"""

import threading
from typing import Protocol, Dict, Any, Optional, List, runtime_checkable
from dataclasses import dataclass


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


def register_runtime(runtime_id: str, factory_or_instance: Any, **metadata) -> None:
    """Register a runtime with the global registry.
    
    Args:
        runtime_id: Unique runtime identifier
        factory_or_instance: Runtime factory function or instance  
        **metadata: Additional metadata for the runtime
        
    Raises:
        RuntimeError: If global registry is not initialized
        ValueError: If runtime_id is already registered
    """
    registry = get_global_registry()
    if registry is None:
        raise RuntimeError(
            "Global runtime registry not initialized. "
            "This should be done by the wrapper layer."
        )
    
    registry.register(runtime_id, factory_or_instance, **metadata)


def resolve_runtime(
    runtime_id: str, 
    config_overrides: Optional[Dict[str, Any]] = None
) -> Any:
    """Resolve a runtime by ID using the global registry.
    
    Args:
        runtime_id: Runtime identifier to resolve
        config_overrides: Optional configuration overrides
        
    Returns:
        Runtime instance
        
    Raises:
        RuntimeError: If global registry is not initialized
        ValueError: If runtime_id is not registered (fail-closed behavior)
    """
    registry = get_global_registry()
    if registry is None:
        raise RuntimeError(
            "Global runtime registry not initialized. "
            "This should be done by the wrapper layer."
        )
    
    return registry.resolve(runtime_id, config_overrides)


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