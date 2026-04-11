"""
Memory Adapter Registry

Provides a registry system for memory adapters to replace hardcoded imports
in memory/memory.py. This enables protocol-driven memory backends without
core modifications.
"""

from typing import Callable, List, Optional, Tuple, Type
from ...utils.adapter_registry import AdapterRegistry
from ..protocols import MemoryProtocol


class MemoryAdapterRegistry(AdapterRegistry[MemoryProtocol]):
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
        super().__init__(adapter_type_name="Memory")


# Default registry instance for backward compatibility
def get_default_memory_registry() -> MemoryAdapterRegistry:
    """Get the default global registry instance for convenience."""
    if not hasattr(get_default_memory_registry, '_default_instance'):
        import threading
        # Use lock for thread safety
        if not hasattr(get_default_memory_registry, '_init_lock'):
            get_default_memory_registry._init_lock = threading.Lock()
        with get_default_memory_registry._init_lock:
            if not hasattr(get_default_memory_registry, '_default_instance'):
                get_default_memory_registry._default_instance = MemoryAdapterRegistry()
    return get_default_memory_registry._default_instance


def register_memory_adapter(name: str, adapter_class: Type[MemoryProtocol]) -> None:
    """Register a memory adapter class."""
    get_default_memory_registry().register_adapter(name, adapter_class)


def register_memory_factory(name: str, factory_func: Callable[..., MemoryProtocol]) -> None:
    """Register a memory adapter factory function."""
    get_default_memory_registry().register_factory(name, factory_func)


def get_memory_adapter(name: str, **kwargs) -> Optional[MemoryProtocol]:
    """Get memory adapter instance by name."""
    return get_default_memory_registry().get_adapter(name, **kwargs)


def list_memory_adapters() -> List[str]:
    """List all registered memory adapter names."""
    return get_default_memory_registry().list_adapters()


# Canonical aliases per AGENTS.md naming conventions
def add_memory_adapter(name: str, adapter_class: Type[MemoryProtocol]) -> None:
    """Canonical alias for register_memory_adapter (preferred naming per AGENTS.md)."""
    return register_memory_adapter(name, adapter_class)


def add_memory_factory(name: str, factory_func: Callable[..., MemoryProtocol]) -> None:
    """Canonical alias for register_memory_factory (preferred naming per AGENTS.md)."""
    return register_memory_factory(name, factory_func)


def has_memory_adapter(name: str) -> bool:
    """Canonical alias for is_available (preferred naming per AGENTS.md)."""
    return get_default_memory_registry().is_available(name)


def get_first_available_memory_adapter(
    preferences: Optional[List[str]] = None, **kwargs
) -> Optional[Tuple[str, MemoryProtocol]]:
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

    return get_default_memory_registry().get_first_available(preferences, **kwargs)


__all__ = [
    'MemoryAdapterRegistry',
    'register_memory_adapter',
    'register_memory_factory', 
    'get_memory_adapter',
    'list_memory_adapters',
    'get_first_available_memory_adapter',
    # Canonical aliases (preferred)
    'add_memory_adapter',
    'add_memory_factory',
    'has_memory_adapter',
]
