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
        self._items: Dict[str, Type[T]] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
        self._lock = threading.Lock()
        
        # Load built-in plugins with error handling
        if builtins:
            for name, loader in builtins.items():
                try:
                    self._items[name] = loader()
                except ImportError:
                    # Built-in plugin dependencies not available, skip
                    pass
                except Exception:
                    # Log other errors but don't crash initialization
                    logger.warning("Failed to load built-in plugin %r", name, exc_info=True)
        
        self._load_entry_points()

    def _load_entry_points(self) -> None:
        """Load plugins from entry points."""
        try:
            for ep in entry_points(group=self._entry_point_group):
                try:
                    plugin_class = ep.load()
                    with self._lock:
                        self._items[ep.name] = plugin_class
                except Exception:
                    # Do not break plugin dispatch because one plugin is broken
                    logger.warning(
                        "Failed to load plugin %r from entry point",
                        ep.name,
                        exc_info=True,
                    )
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
            if normalized_name in self._items:
                # Remove all aliases pointing to this plugin
                aliases_to_remove = [
                    alias for alias, canonical in self._aliases.items()
                    if canonical == normalized_name
                ]
                for alias in aliases_to_remove:
                    del self._aliases[alias]
                
                del self._items[normalized_name]
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
        with self._lock:
            normalized_name = name.lower()
            
            # Resolve alias to canonical name
            canonical_name = self._aliases.get(normalized_name, normalized_name)
            cls = self._items.get(canonical_name)
            
            # Capture available plugins snapshot while holding lock
            # to avoid race condition between check and error message
            if cls is None:
                available_plugins = sorted(self._items.keys())
                available_aliases = sorted(self._aliases.keys())
                available_snapshot = available_plugins + available_aliases
            else:
                available_snapshot = None
        
        if cls is None:
            raise ValueError(
                f"Unknown {self._entry_point_group} plugin: {name!r}. "
                f"Available: {available_snapshot}"
            )
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
            return sorted(self._items.keys())

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
            return sorted(list(self._items.keys()) + list(self._aliases.keys()))