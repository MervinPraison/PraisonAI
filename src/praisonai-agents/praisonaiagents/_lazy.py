"""
Centralized lazy loading utility for zero-overhead imports.

This module provides DRY utilities for lazy loading across the praisonaiagents package.
All heavy dependencies should use these utilities to ensure consistent behavior and
thread-safe caching.

Usage:
    # Simple lazy import
    from praisonaiagents._lazy import lazy_import
    HookEvent = lazy_import('praisonaiagents.hooks.types', 'HookEvent')
    
    # Create a __getattr__ function for a module
    from praisonaiagents._lazy import create_lazy_getattr
    
    _LAZY_IMPORTS = {
        'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
        'HookResult': ('praisonaiagents.hooks.types', 'HookResult'),
    }
    
    __getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
"""

import importlib
import threading
from typing import Any, Callable, Dict, Optional, Tuple

# Global cache lock for thread-safe access
_cache_lock = threading.Lock()

# Global module cache
_module_cache: Dict[str, Any] = {}


def lazy_import(
    module_path: str,
    attr_name: str,
    cache: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Lazily import an attribute from a module with thread-safe caching.
    
    Args:
        module_path: Full module path (e.g., 'praisonaiagents.hooks.types')
        attr_name: Attribute name to import (e.g., 'HookEvent')
        cache: Optional cache dict (uses global cache if None)
    
    Returns:
        The imported attribute
    
    Raises:
        ModuleNotFoundError: If the module doesn't exist
        AttributeError: If the attribute doesn't exist in the module
    
    Example:
        HookEvent = lazy_import('praisonaiagents.hooks.types', 'HookEvent')
    """
    cache = cache if cache is not None else _module_cache
    cache_key = f"{module_path}.{attr_name}"
    
    # Fast path: check cache without lock
    if cache_key in cache:
        return cache[cache_key]
    
    # Slow path: acquire lock and import
    with _cache_lock:
        # Double-check after acquiring lock
        if cache_key in cache:
            return cache[cache_key]
        
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        cache[cache_key] = value
        return value


class LazyModule:
    """
    A lazy module wrapper that defers import until first attribute access.
    
    Useful for creating module-level lazy imports that behave like the real module.
    
    Example:
        _hooks_types = LazyModule('praisonaiagents.hooks.types')
        # Module not loaded yet
        
        HookEvent = _hooks_types.HookEvent
        # Now module is loaded and cached
    """
    
    __slots__ = ('_module_path', '_module', '_lock')
    
    def __init__(self, module_path: str):
        object.__setattr__(self, '_module_path', module_path)
        object.__setattr__(self, '_module', None)
        object.__setattr__(self, '_lock', threading.Lock())
    
    def _load_module(self) -> Any:
        """Load the module if not already loaded."""
        if self._module is None:
            with self._lock:
                if self._module is None:
                    module = importlib.import_module(self._module_path)
                    object.__setattr__(self, '_module', module)
        return self._module
    
    def __getattr__(self, name: str) -> Any:
        module = self._load_module()
        return getattr(module, name)
    
    def __repr__(self) -> str:
        loaded = "loaded" if self._module is not None else "not loaded"
        return f"<LazyModule '{self._module_path}' ({loaded})>"


def create_lazy_getattr(
    mapping: Dict[str, Tuple[str, str]],
    module_name: str = 'unknown',
    cache: Optional[Dict[str, Any]] = None
) -> Callable[[str], Any]:
    """
    Create a __getattr__ function for lazy loading module attributes.
    
    This is the DRY way to implement lazy loading in __init__.py files.
    
    Args:
        mapping: Dict mapping attribute names to (module_path, attr_name) tuples
        module_name: Name of the module (for error messages)
        cache: Optional cache dict (creates new one if None)
    
    Returns:
        A __getattr__ function suitable for use in a module
    
    Example:
        # In __init__.py
        from praisonaiagents._lazy import create_lazy_getattr
        
        _LAZY_IMPORTS = {
            'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
            'HookResult': ('praisonaiagents.hooks.types', 'HookResult'),
        }
        
        __getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
    """
    _cache = cache if cache is not None else {}
    
    def __getattr__(name: str) -> Any:
        # Check cache first
        if name in _cache:
            return _cache[name]
        
        # Check if it's in our mapping
        if name in mapping:
            module_path, attr_name = mapping[name]
            value = lazy_import(module_path, attr_name, _cache)
            _cache[name] = value
            return value
        
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")
    
    return __getattr__


def create_lazy_getattr_with_fallback(
    mapping: Dict[str, Tuple[str, str]],
    module_name: str = 'unknown',
    cache: Optional[Dict[str, Any]] = None,
    fallback_modules: Optional[list] = None,
    custom_handler: Optional[Callable[[str, Dict[str, Any]], Any]] = None
) -> Callable[[str], Any]:
    """
    Create a __getattr__ function with fallback to sub-packages.
    
    This is useful for main __init__.py files that need to:
    1. Check a mapping of known lazy imports
    2. Fall back to sub-packages for additional symbols
    3. Handle custom logic for optional modules
    
    Args:
        mapping: Dict mapping attribute names to (module_path, attr_name) tuples
        module_name: Name of the module (for error messages)
        cache: Optional cache dict (creates new one if None)
        fallback_modules: List of sub-package names to try if not in mapping
        custom_handler: Optional function(name, cache) for custom logic before fallback
    
    Returns:
        A __getattr__ function suitable for use in a module
    """
    _cache = cache if cache is not None else {}
    _fallback_modules = fallback_modules or []
    
    def __getattr__(name: str) -> Any:
        # Check cache first
        if name in _cache:
            return _cache[name]
        
        # Check if it's in our mapping
        if name in mapping:
            module_path, attr_name = mapping[name]
            try:
                value = lazy_import(module_path, attr_name, _cache)
                _cache[name] = value
                return value
            except (ImportError, AttributeError):
                # Optional module not available
                _cache[name] = None
                return None
        
        # Try custom handler if provided
        if custom_handler is not None:
            try:
                result = custom_handler(name, _cache)
                if result is not None:
                    _cache[name] = result
                    return result
            except AttributeError:
                pass  # Continue to fallback
        
        # Try fallback modules
        for subpkg in _fallback_modules:
            try:
                submodule = importlib.import_module(f'.{subpkg}', module_name)
                if hasattr(submodule, name):
                    result = getattr(submodule, name)
                    _cache[name] = result
                    return result
            except (ImportError, AttributeError):
                continue
        
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")
    
    return __getattr__


def create_lazy_getattr_with_groups(
    groups: Dict[str, Dict[str, Tuple[str, str]]],
    module_name: str = 'unknown',
    cache: Optional[Dict[str, Any]] = None
) -> Callable[[str], Any]:
    """
    Create a __getattr__ function with grouped lazy imports.
    
    When one attribute from a group is accessed, all attributes in that group
    are imported together. This is useful when multiple attributes come from
    the same module and are often used together.
    
    Args:
        groups: Dict mapping group names to dicts of (attr_name -> (module_path, attr_name))
        module_name: Name of the module (for error messages)
        cache: Optional cache dict (creates new one if None)
    
    Returns:
        A __getattr__ function suitable for use in a module
    
    Example:
        _LAZY_GROUPS = {
            'types': {
                'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
                'HookResult': ('praisonaiagents.hooks.types', 'HookResult'),
            },
            'events': {
                'BeforeToolInput': ('praisonaiagents.hooks.events', 'BeforeToolInput'),
                'AfterToolInput': ('praisonaiagents.hooks.events', 'AfterToolInput'),
            },
        }
        
        __getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)
    """
    _cache = cache if cache is not None else {}
    
    # Build reverse mapping: attr_name -> group_name
    _attr_to_group: Dict[str, str] = {}
    for group_name, attrs in groups.items():
        for attr_name in attrs:
            _attr_to_group[attr_name] = group_name
    
    def __getattr__(name: str) -> Any:
        # Check cache first
        if name in _cache:
            return _cache[name]
        
        # Check if it's in our groups
        if name in _attr_to_group:
            group_name = _attr_to_group[name]
            group = groups[group_name]
            
            # Import all attributes in the group
            for attr_name, (module_path, real_attr_name) in group.items():
                if attr_name not in _cache:
                    value = lazy_import(module_path, real_attr_name)
                    _cache[attr_name] = value
            
            return _cache[name]
        
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")
    
    return __getattr__
