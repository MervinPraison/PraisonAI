"""
Knowledge Adapter Registry

Provides a registry system for knowledge adapters to replace hardcoded imports
in knowledge/knowledge.py. This enables protocol-driven knowledge backends without
core modifications.
"""

from typing import Callable, List, Optional, Tuple, Type
from ...utils.adapter_registry import AdapterRegistry
from ..protocols import KnowledgeStoreProtocol


class KnowledgeAdapterRegistry(AdapterRegistry[KnowledgeStoreProtocol]):
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
        super().__init__(adapter_type_name="Knowledge")


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


def list_knowledge_adapters() -> List[str]:
    """List all registered knowledge adapter names."""
    return _knowledge_registry.list_adapters()


def get_first_available_knowledge_adapter(
    preferences: Optional[List[str]] = None, **kwargs
) -> Optional[Tuple[str, KnowledgeStoreProtocol]]:
    """
    Get first available knowledge adapter.

    Args:
        preferences: List of adapter names to try (defaults to ["mem0", "mongodb"])
        **kwargs: Configuration passed to adapter constructor

    Returns:
        (adapter_name, adapter_instance) tuple or None
    """
    if preferences is None:
        # Default to actual available adapters per knowledge/adapters/__init__.py
        preferences = ["mem0", "mongodb"]

    return _knowledge_registry.get_first_available(preferences, **kwargs)


# Canonical aliases per AGENTS.md naming conventions
def add_knowledge_adapter(name: str, adapter_class: Type[KnowledgeStoreProtocol]) -> None:
    """Canonical alias for register_knowledge_adapter (preferred naming per AGENTS.md)."""
    return register_knowledge_adapter(name, adapter_class)


def add_knowledge_factory(name: str, factory_func: Callable[..., KnowledgeStoreProtocol]) -> None:
    """Canonical alias for register_knowledge_factory (preferred naming per AGENTS.md)."""
    return register_knowledge_factory(name, factory_func)


def has_knowledge_adapter(name: str) -> bool:
    """Canonical alias for is_available (preferred naming per AGENTS.md)."""
    return _knowledge_registry.is_available(name)


__all__ = [
    'KnowledgeAdapterRegistry',
    'register_knowledge_adapter',
    'register_knowledge_factory',
    'get_knowledge_adapter',
    'list_knowledge_adapters',
    'get_first_available_knowledge_adapter',
    # Canonical aliases (preferred)
    'add_knowledge_adapter',
    'add_knowledge_factory',
    'has_knowledge_adapter',
]
