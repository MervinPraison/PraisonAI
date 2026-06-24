"""
Tool registry for explicit tool management.

Replaces the globals() side-channel pattern with an explicit,
per-instance tool registry that is the single source of truth
for both builtin and user tools.
"""

import logging
import threading
import weakref
from typing import Dict, Callable, List, Optional, Any
import inspect

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing tools in a scoped, explicit manner."""
    
    def __init__(self):
        self._functions: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._resolvers: List[weakref.ref] = []  # Track multiple resolvers with weak refs
        
    def register_function(self, name: str, func: Callable) -> None:
        """Register a function tool."""
        if not callable(func):
            raise ValueError(f"Tool {name} must be callable")
        with self._lock:
            self._functions[name] = func
        logger.debug(f"Registered function tool: {name}")
        # Invalidate all resolver caches for this tool
        self._notify_invalidate(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """Get a function tool by name."""
        with self._lock:
            return self._functions.get(name)

    def list_functions(self) -> List[str]:
        """List all registered function tool names."""
        with self._lock:
            return list(self._functions.keys())

    def get_functions_dict(self) -> Dict[str, Callable]:
        """Get a copy of all registered functions."""
        with self._lock:
            return dict(self._functions)
    
    def clear(self) -> None:
        """Clear all registered tools."""
        with self._lock:
            self._functions.clear()
        logger.debug("Cleared tool registry")
        # Invalidate all resolver caches
        self._notify_invalidate()
    
    def set_resolver(self, resolver) -> None:
        """Set the resolver for cache invalidation.
        
        Args:
            resolver: ToolResolver instance to notify on changes
        """
        with self._lock:
            self._resolvers.append(weakref.ref(resolver))
    
    def _notify_invalidate(self, name: Optional[str] = None) -> None:
        """Notify all resolvers to invalidate their caches.
        
        Args:
            name: Optional tool name to invalidate. If None, invalidate all.
        """
        with self._lock:
            alive = []
            for ref in self._resolvers:
                r = ref()
                if r is not None:
                    alive.append(ref)
            # Clean up dead references
            self._resolvers = alive
        
        # Notify outside lock to avoid holding lock during external calls
        for ref in alive:
            r = ref()
            if r is not None:
                r.invalidate(name)
    
    def register_from_module(self, module: Any) -> List[str]:
        """
        Register all callable functions from a module.
        
        Args:
            module: Module object to scan for functions
            
        Returns:
            List of registered function names
        """
        registered = []
        for name, obj in inspect.getmembers(module):
            if (not name.startswith('_') and 
                callable(obj) and 
                not inspect.isclass(obj)):
                self.register_function(name, obj)  # This already acquires the lock
                registered.append(name)
        
        logger.debug(f"Registered {len(registered)} functions from module: {registered}")
        return registered

    def __len__(self) -> int:
        """Return total number of registered tools."""
        with self._lock:
            return len(self._functions)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool function is registered."""
        with self._lock:
            return name in self._functions
