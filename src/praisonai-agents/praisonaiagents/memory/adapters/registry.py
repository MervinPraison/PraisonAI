"""
Memory Adapter Registry

Provides a registry system for memory adapters to replace hardcoded imports
in memory/memory.py. This enables protocol-driven memory backends without
core modifications.
"""

import threading
from typing import Dict, Type, Any, Optional, Callable
from ..protocols import MemoryProtocol


class MemoryAdapterRegistry:
    """
    Thread-safe registry for memory adapters.
    
    Replaces hardcoded _check_chromadb, _check_mem0, etc. in memory.py
    with dynamic adapter discovery and instantiation.
    
    Example:
        ```python
        # Register adapter (typically done on import)
        register_memory_adapter("sqlite", SQLiteAdapter)
        register_memory_adapter("chroma", ChromaAdapter)  # in wrapper
        
        # Use in Memory class
        adapter = get_memory_adapter("chroma", config=config)
        ```
    """
    
    def __init__(self):
        self._adapters: Dict[str, Type[MemoryProtocol]] = {}
        self._factories: Dict[str, Callable[..., MemoryProtocol]] = {}
        self._lock = threading.Lock()
    
    def register_adapter(self, name: str, adapter_class: Type[MemoryProtocol]) -> None:
        """
        Register a memory adapter class.
        
        Args:
            name: Adapter name (e.g., "sqlite", "chroma", "mem0")
            adapter_class: Class implementing MemoryProtocol
        """
        with self._lock:
            self._adapters[name] = adapter_class
    
    def register_factory(self, name: str, factory_func: Callable[..., MemoryProtocol]) -> None:
        """
        Register a memory adapter factory function.
        
        Args:
            name: Adapter name
            factory_func: Function that creates adapter instances
        """
        with self._lock:
            self._factories[name] = factory_func
    
    def get_adapter(self, name: str, **kwargs) -> Optional[MemoryProtocol]:
        """
        Get memory adapter instance by name.
        
        Args:
            name: Adapter name
            **kwargs: Configuration passed to adapter constructor
            
        Returns:
            Memory adapter instance or None if not found
        """
        with self._lock:
            # Try factory first (more flexible)
            if name in self._factories:
                try:
                    return self._factories[name](**kwargs)
                except Exception:
                    # Factory failed, fall through to class instantiation
                    pass
            
            # Try direct class instantiation
            if name in self._adapters:
                try:
                    return self._adapters[name](**kwargs)
                except Exception:
                    # Class instantiation failed
                    pass
        
        return None
    
    def list_adapters(self) -> list[str]:
        """List all registered adapter names."""
        with self._lock:
            return sorted(set(self._adapters.keys()) | set(self._factories.keys()))
    
    def is_available(self, name: str) -> bool:
        """Check if adapter is available (registered and can be instantiated)."""
        with self._lock:
            return name in self._adapters or name in self._factories
    
    def get_first_available(self, preferences: list[str], **kwargs) -> Optional[tuple[str, MemoryProtocol]]:
        """
        Get first available adapter from preference list.
        
        Args:
            preferences: List of adapter names in order of preference
            **kwargs: Configuration passed to adapter constructor
            
        Returns:
            (adapter_name, adapter_instance) tuple or None
        """
        for name in preferences:
            adapter = self.get_adapter(name, **kwargs)
            if adapter is not None:
                return name, adapter
        return None


# Global registry instance
_memory_registry = MemoryAdapterRegistry()


def register_memory_adapter(name: str, adapter_class: Type[MemoryProtocol]) -> None:
    """Register a memory adapter class."""
    _memory_registry.register_adapter(name, adapter_class)


def register_memory_factory(name: str, factory_func: Callable[..., MemoryProtocol]) -> None:
    """Register a memory adapter factory function."""
    _memory_registry.register_factory(name, factory_func)


def get_memory_adapter(name: str, **kwargs) -> Optional[MemoryProtocol]:
    """Get memory adapter instance by name."""
    return _memory_registry.get_adapter(name, **kwargs)


def list_memory_adapters() -> list[str]:
    """List all registered memory adapter names."""
    return _memory_registry.list_adapters()


def get_first_available_memory_adapter(preferences: list[str] = None, **kwargs) -> Optional[tuple[str, MemoryProtocol]]:
    """
    Get first available memory adapter.
    
    Args:
        preferences: List of adapter names to try (defaults to ["sqlite", "in_memory"])
        **kwargs: Configuration passed to adapter constructor
        
    Returns:
        (adapter_name, adapter_instance) tuple or None
    """
    if preferences is None:
        preferences = ["sqlite", "in_memory"]
    
    return _memory_registry.get_first_available(preferences, **kwargs)


__all__ = [
    'MemoryAdapterRegistry',
    'register_memory_adapter', 
    'register_memory_factory',
    'get_memory_adapter',
    'list_memory_adapters',
    'get_first_available_memory_adapter',
]