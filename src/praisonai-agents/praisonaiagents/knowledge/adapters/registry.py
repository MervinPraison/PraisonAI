"""
Knowledge Adapter Registry

Provides a registry system for knowledge adapters to replace hardcoded imports
in knowledge/knowledge.py. This enables protocol-driven knowledge backends without
core modifications.
"""

import threading
from typing import Dict, Type, Any, Optional, Callable
from ..protocols import KnowledgeStoreProtocol


class KnowledgeAdapterRegistry:
    """
    Thread-safe registry for knowledge adapters.
    
    Replaces hardcoded imports and configurations in knowledge.py
    with dynamic adapter discovery and instantiation.
    
    Example:
        ```python
        # Register adapter (typically done on import)
        register_knowledge_adapter("sqlite", SQLiteKnowledgeAdapter)
        register_knowledge_adapter("chroma", ChromaAdapter)  # in wrapper
        
        # Use in Knowledge class
        adapter = get_knowledge_adapter("chroma", config=config)
        ```
    """
    
    def __init__(self):
        self._adapters: Dict[str, Type[KnowledgeStoreProtocol]] = {}
        self._factories: Dict[str, Callable[..., KnowledgeStoreProtocol]] = {}
        self._lock = threading.Lock()
    
    def register_adapter(self, name: str, adapter_class: Type[KnowledgeStoreProtocol]) -> None:
        """
        Register a knowledge adapter class.
        
        Args:
            name: Adapter name (e.g., "sqlite", "chroma", "mem0")
            adapter_class: Class implementing KnowledgeStoreProtocol
        """
        with self._lock:
            self._adapters[name] = adapter_class
    
    def register_factory(self, name: str, factory_func: Callable[..., KnowledgeStoreProtocol]) -> None:
        """
        Register a knowledge adapter factory function.
        
        Args:
            name: Adapter name
            factory_func: Function that creates adapter instances
        """
        with self._lock:
            self._factories[name] = factory_func
    
    def get_adapter(self, name: str, **kwargs) -> Optional[KnowledgeStoreProtocol]:
        """
        Get knowledge adapter instance by name.
        
        Args:
            name: Adapter name
            **kwargs: Configuration passed to adapter constructor
            
        Returns:
            Knowledge adapter instance or None if not found
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
    
    def get_first_available(self, preferences: list[str], **kwargs) -> Optional[tuple[str, KnowledgeStoreProtocol]]:
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
_knowledge_registry = KnowledgeAdapterRegistry()


def register_knowledge_adapter(name: str, adapter_class: Type[KnowledgeStoreProtocol]) -> None:
    """Register a knowledge adapter class."""
    _knowledge_registry.register_adapter(name, adapter_class)


def register_knowledge_factory(name: str, factory_func: Callable[..., KnowledgeStoreProtocol]) -> None:
    """Register a knowledge adapter factory function."""
    _knowledge_registry.register_factory(name, factory_func)


def get_knowledge_adapter(name: str, **kwargs) -> Optional[KnowledgeStoreProtocol]:
    """Get knowledge adapter instance by name."""
    return _knowledge_registry.get_adapter(name, **kwargs)


def list_knowledge_adapters() -> list[str]:
    """List all registered knowledge adapter names."""
    return _knowledge_registry.list_adapters()


def get_first_available_knowledge_adapter(preferences: list[str] = None, **kwargs) -> Optional[tuple[str, KnowledgeStoreProtocol]]:
    """
    Get first available knowledge adapter.
    
    Args:
        preferences: List of adapter names to try (defaults to ["sqlite", "in_memory"])
        **kwargs: Configuration passed to adapter constructor
        
    Returns:
        (adapter_name, adapter_instance) tuple or None
    """
    if preferences is None:
        preferences = ["sqlite", "in_memory"]
    
    return _knowledge_registry.get_first_available(preferences, **kwargs)


__all__ = [
    'KnowledgeAdapterRegistry',
    'register_knowledge_adapter', 
    'register_knowledge_factory',
    'get_knowledge_adapter',
    'list_knowledge_adapters',
    'get_first_available_knowledge_adapter',
]