"""Generic plugin registry implementation for PraisonAI.

This module provides a unified registry pattern to replace the divergent singleton
implementations across the codebase. It supports both built-in and entry-point
based plugin discovery with thread-safe registration and dependency injection.
"""

from __future__ import annotations

import threading
from importlib.metadata import entry_points
from typing import Callable, Dict, Generic, Optional, Type, TypeVar
import logging

T = TypeVar("T")
logger = logging.getLogger(__name__)


class PluginRegistry(Generic[T]):
    # Guards creation of per-subclass default-instance locks
    _default_locks_guard = threading.Lock()
    """Generic plugin registry: builtins + entry points + runtime register().
    
    This replaces the singleton pattern with dependency injection while maintaining
    the same functionality. Supports:
    - Built-in plugins with lazy loading
    - Entry points discovery
    - Runtime registration
    - Alias support for alternative names
    - Thread-safe operations
    """

    def __init__(
        self, 
        *,
        entry_point_group: str,
        builtins: Optional[Dict[str, Callable[[], Type[T]]]] = None
    ) -> None:
        """Initialize the registry.
        
        Args:
            entry_point_group: Entry points group name for plugin discovery
            builtins: Dict of name -> loader function for built-in plugins
        """
        self._entry_point_group = entry_point_group
        self._loaders: Dict[str, Callable[[], Type[T]]] = {}  # lazy loaders
        self._items: Dict[str, Type[T]] = {}  # resolved cache
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
        self._lock = threading.RLock()  # Use RLock for re-entrant access
        
        # Store built-in loaders (normalized) without calling them
        if builtins:
            for name, loader in builtins.items():
                self._add_loader(name, loader)
        
        self._discover_entry_points()

    def _add_loader(self, name: str, loader: Callable[[], Type[T]]) -> None:
        """Add a loader with normalized name."""
        normalized_name = name.lower()
        self._loaders[normalized_name] = loader

    def _discover_entry_points(self) -> None:
        """Discover entry point loaders without loading them."""
        try:
            for ep in entry_points(group=self._entry_point_group):
                self._add_loader(ep.name, ep.load)
        except Exception:
            # entry_points() might not be available in older Python versions
            logger.debug("Entry points not available for group %s", self._entry_point_group)

    def register(
        self, 
        name: str, 
        cls: Type[T], 
        *, 
        aliases: Optional[list[str]] = None
    ) -> None:
        """Register a plugin at runtime.
        
        Args:
            name: Plugin name
            cls: Plugin class
            aliases: Optional list of alias names for this plugin
        """
        with self._lock:
            canonical_name = name.lower()
            # Store both in loaders (for consistency with discovery) and items (for immediate access)
            self._loaders[canonical_name] = lambda: cls
            self._items[canonical_name] = cls
            
            # Register aliases
            if aliases:
                for alias in aliases:
                    normalized_alias = alias.lower()
                    self._aliases[normalized_alias] = canonical_name

    def unregister(self, name: str) -> bool:
        """Unregister a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            True if plugin was found and removed, False otherwise
        """
        with self._lock:
            normalized_name = name.lower()
            
            # Check if it's an alias
            if normalized_name in self._aliases:
                del self._aliases[normalized_name]
                return True
            
            # Check if it's a canonical name
            if normalized_name in self._loaders:
                # Remove all aliases pointing to this plugin
                aliases_to_remove = [
                    alias for alias, canonical in self._aliases.items()
                    if canonical == normalized_name
                ]
                for alias in aliases_to_remove:
                    del self._aliases[alias]
                
                # Remove from both loaders and items cache
                del self._loaders[normalized_name]
                self._items.pop(normalized_name, None)
                return True
            
            return False

    def resolve(self, name: str) -> Type[T]:
        """Resolve a plugin name to its class.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin class
            
        Raises:
            ValueError: If plugin is not found
        """
        normalized_name = name.lower()
        
        with self._lock:
            # Check cache first
            canonical_name = self._aliases.get(normalized_name, normalized_name)
            cls = self._items.get(canonical_name)
            
            if cls is not None:
                return cls
            
            # Try to load from loaders
            loader = self._loaders.get(canonical_name)
            if loader is None:
                # Capture available plugins snapshot while holding lock
                available_loaders = sorted(self._loaders.keys())
                available_aliases = sorted(self._aliases.keys())
                available_snapshot = available_loaders + available_aliases
                raise ValueError(
                    f"Unknown {self._entry_point_group} plugin: {name!r}. "
                    f"Available: {available_snapshot}"
                )
            
            # Load and cache the plugin (release lock during loading to prevent deadlock)
            pass
        
        # Load outside the lock to prevent deadlock if loader calls back into registry
        try:
            cls = loader()
        except ImportError as e:
            raise ValueError(
                f"Plugin {name!r} is registered but its dependencies "
                f"are not installed: {e}"
            ) from e
        
        # Re-acquire lock to cache the result
        with self._lock:
            self._items[canonical_name] = cls
            return cls

    def create(self, name: str, *args, **kwargs) -> T:
        """Create an instance of the specified plugin.
        
        Args:
            name: Plugin name
            *args, **kwargs: Arguments to pass to plugin constructor
            
        Returns:
            Plugin instance
            
        Raises:
            ValueError: If plugin is not found
        """
        cls = self.resolve(name)
        return cls(*args, **kwargs)

    def list_names(self) -> list[str]:
        """List all registered plugin names.
        
        Returns:
            Sorted list of plugin names
        """
        with self._lock:
            return sorted(self._loaders.keys())

    def is_available(self, name: str) -> bool:
        """Check if a plugin is available.
        
        Args:
            name: Plugin name
            
        Returns:
            True if plugin exists and can be created
        """
        try:
            self.resolve(name)
            return True
        except ValueError:
            return False

    def list_aliases(self) -> Dict[str, str]:
        """List all aliases and their target plugins.
        
        Returns:
            Dict mapping alias -> canonical name
        """
        with self._lock:
            return dict(self._aliases)

    def list_all_names(self) -> list[str]:
        """List all names including aliases.
        
        Returns:
            Sorted list of all registered names and aliases
        """
        with self._lock:
            return sorted(list(self._loaders.keys()) + list(self._aliases.keys()))
    
    def get_by_attr(self, module_name: str, attr_name: str) -> Type[T]:
        """Get a plugin by attribute name for __getattr__ dispatch.
        
        Args:
            module_name: Module name requesting the attribute (for error messages)
            attr_name: Attribute name to resolve
            
        Returns:
            Plugin class
            
        Raises:
            AttributeError: If plugin is not found
        """
        try:
            return self.resolve(attr_name)
        except ValueError:
            raise AttributeError(f"module {module_name!r} has no attribute {attr_name!r}")

    @classmethod
    def default(cls) -> "PluginRegistry[T]":
        """
        Process-default registry. Prefer DI; use this only at the edge.
        
        Provides thread-safe lazy initialization of default instances per-subclass.
        Each subclass gets its own default instance cache.
        """
        # Use a class-level cache stored in the subclass's __dict__
        cache_key = "_default_instance"
        lock_key = "_default_instance_lock"
        
        # Get or create lock in subclass __dict__ (not shared across inheritance hierarchy)
        if lock_key not in cls.__dict__:
            # Thread-safe initialization of the per-subclass lock itself
            with PluginRegistry._default_locks_guard:
                if lock_key not in cls.__dict__:
                    # Store directly in the class __dict__ to avoid inheritance sharing
                    setattr(cls, lock_key, threading.Lock())
        
        lock = getattr(cls, lock_key)
        
        # Check cache first (without lock for performance)
        cache = cls.__dict__.get(cache_key)
        if cache is not None:
            return cache
        
        # Double-checked locking pattern
        with lock:
            cache = cls.__dict__.get(cache_key)
            if cache is None:
                cache = cls()
                # Store directly in the class __dict__ to ensure per-subclass isolation
                setattr(cls, cache_key, cache)
            return cache


def create_lazy_getattr(registry: PluginRegistry[T]) -> Callable[[str], T]:
    """Create a __getattr__ function backed by a PluginRegistry.
    
    This replaces manual if/elif ladders in __init__.py files with a data-driven
    approach using the plugin registry.
    
    Args:
        registry: The plugin registry to use for resolution
        
    Returns:
        Function that can be used as __getattr__ in a module
        
    Example:
        # In __init__.py:
        from ._registry import create_lazy_getattr
        
        # Assuming you have a registry instance
        __getattr__ = create_lazy_getattr(my_registry)
    """
    def __getattr__(name: str) -> T:
        try:
            plugin_class = registry.resolve(name)
            return plugin_class
        except ValueError:
            # Get the calling module name for error context
            import inspect
            frame = inspect.currentframe()
            if frame and frame.f_back:
                module_name = frame.f_back.f_globals.get('__name__', 'unknown')
            else:
                module_name = 'unknown'
            
            raise AttributeError(f"module {module_name!r} has no attribute {name!r}")
    
    return __getattr__
