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
        # Note: AutoGen-specific adapters moved to framework_adapters.autogen
        
    def register_function(self, name: str, func: Callable) -> None:
        """Register a function tool."""
        if not callable(func):
            raise ValueError(f"Tool {name} must be callable")
        with self._lock:
            self._functions[name] = func
        logger.debug(f"Registered function tool: {name}")
        # Invalidate all resolver caches for this tool
        self._notify_invalidate(name)
    
    def register_autogen_adapter(self, tool_type_name: str, adapter: Callable, _suppress_deprecation_warning: bool = False) -> None:
        """Deprecated: AutoGen adapters moved to framework_adapters.autogen module."""
        if not _suppress_deprecation_warning:
            import warnings
            warnings.warn(
                "ToolRegistry.register_autogen_adapter is deprecated. "
                "AutoGen-specific logic has been moved to framework_adapters.autogen module.",
                DeprecationWarning,
                stacklevel=2
            )
        # For backward compatibility, still store but warn
        if not callable(adapter):
            raise ValueError(f"AutoGen adapter for {tool_type_name} must be callable")
        with self._lock:
            if not hasattr(self, '_autogen_adapters'):
                self._autogen_adapters: Dict[str, Callable] = {}
            self._autogen_adapters[tool_type_name] = adapter
        logger.debug(f"Registered AutoGen adapter: {tool_type_name} (deprecated)")
    
    def get_function(self, name: str) -> Optional[Callable]:
        """Get a function tool by name."""
        with self._lock:
            return self._functions.get(name)
    
    def get_autogen_adapter(self, tool_type_name: str) -> Optional[Callable]:
        """Deprecated: AutoGen adapters moved to framework_adapters.autogen module."""
        import warnings
        warnings.warn(
            "ToolRegistry.get_autogen_adapter is deprecated. "
            "AutoGen-specific logic has been moved to framework_adapters.autogen module.",
            DeprecationWarning,
            stacklevel=2
        )
        # For backward compatibility
        if hasattr(self, '_autogen_adapters'):
            with self._lock:
                return self._autogen_adapters.get(tool_type_name)
        return None
    
    def list_functions(self) -> List[str]:
        """List all registered function tool names."""
        with self._lock:
            return list(self._functions.keys())
    
    def list_autogen_adapters(self) -> List[str]:
        """Deprecated: AutoGen adapters moved to framework_adapters.autogen module."""
        import warnings
        warnings.warn(
            "ToolRegistry.list_autogen_adapters is deprecated. "
            "AutoGen-specific logic has been moved to framework_adapters.autogen module.",
            DeprecationWarning,
            stacklevel=2
        )
        # For backward compatibility
        if hasattr(self, '_autogen_adapters'):
            with self._lock:
                return list(self._autogen_adapters.keys())
        return []
    
    def get_functions_dict(self) -> Dict[str, Callable]:
        """Get a copy of all registered functions."""
        with self._lock:
            return dict(self._functions)
    
    def clear(self) -> None:
        """Clear all registered tools."""
        with self._lock:
            self._functions.clear()
            if hasattr(self, '_autogen_adapters'):
                self._autogen_adapters.clear()
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
    
    def register_builtin_autogen_adapters(self, _suppress_deprecation_warning: bool = False) -> None:
        """Deprecated: AutoGen adapters moved to framework_adapters.autogen module."""
        if not _suppress_deprecation_warning:
            import warnings
            warnings.warn(
                "ToolRegistry.register_builtin_autogen_adapters is deprecated. "
                "AutoGen-specific logic has been moved to framework_adapters.autogen module.",
                DeprecationWarning,
                stacklevel=2
            )
        # For backward compatibility, attempt old logic but warn
        try:
            from .inbuilt_tools import _get_autogen_tools
            tools_module = _get_autogen_tools()
            if tools_module:
                for attr_name in dir(tools_module):
                    if attr_name.startswith('autogen_') and not attr_name.startswith('__'):
                        adapter = getattr(tools_module, attr_name)
                        if callable(adapter):
                            tool_type_name = attr_name.replace('autogen_', '')
                            self.register_autogen_adapter(tool_type_name, adapter, _suppress_deprecation_warning=True)
        except ImportError as e:
            logger.warning(f"Could not register builtin AutoGen adapters: {e}")
        except Exception as e:
            logger.warning(f"Error registering builtin AutoGen adapters: {e}")
    
    def __len__(self) -> int:
        """Return total number of registered tools."""
        with self._lock:
            autogen_count = len(self._autogen_adapters) if hasattr(self, '_autogen_adapters') else 0
            return len(self._functions) + autogen_count
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool function is registered."""
        with self._lock:
            return name in self._functions
