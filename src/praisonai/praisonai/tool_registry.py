"""
Tool registry for explicit tool management.

Replaces the globals() side-channel pattern with an explicit,
per-instance tool registry that is the single source of truth
for both builtin and user tools.
"""

import logging
from typing import Dict, Callable, List, Optional, Any
import inspect

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing tools in a scoped, explicit manner."""
    
    def __init__(self):
        self._functions: Dict[str, Callable] = {}
        self._autogen_adapters: Dict[str, Callable] = {}
        
    def register_function(self, name: str, func: Callable) -> None:
        """Register a function tool."""
        if not callable(func):
            raise ValueError(f"Tool {name} must be callable")
        self._functions[name] = func
        logger.debug(f"Registered function tool: {name}")
    
    def register_autogen_adapter(self, tool_type_name: str, adapter: Callable) -> None:
        """Register an AutoGen-specific tool adapter."""
        if not callable(adapter):
            raise ValueError(f"AutoGen adapter for {tool_type_name} must be callable")
        self._autogen_adapters[tool_type_name] = adapter
        logger.debug(f"Registered AutoGen adapter: {tool_type_name}")
    
    def get_function(self, name: str) -> Optional[Callable]:
        """Get a function tool by name."""
        return self._functions.get(name)
    
    def get_autogen_adapter(self, tool_type_name: str) -> Optional[Callable]:
        """Get an AutoGen adapter by tool type name."""
        return self._autogen_adapters.get(tool_type_name)
    
    def list_functions(self) -> List[str]:
        """List all registered function tool names."""
        return list(self._functions.keys())
    
    def list_autogen_adapters(self) -> List[str]:
        """List all registered AutoGen adapter names."""
        return list(self._autogen_adapters.keys())
    
    def get_functions_dict(self) -> Dict[str, Callable]:
        """Get a copy of all registered functions."""
        return dict(self._functions)
    
    def clear(self) -> None:
        """Clear all registered tools."""
        self._functions.clear()
        self._autogen_adapters.clear()
        logger.debug("Cleared tool registry")
    
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
                self.register_function(name, obj)
                registered.append(name)
        
        logger.debug(f"Registered {len(registered)} functions from module: {registered}")
        return registered
    
    def register_builtin_autogen_adapters(self) -> None:
        """Register builtin AutoGen adapters from inbuilt_tools."""
        try:
            # Lazy import to avoid circular dependencies
            from .inbuilt_tools import _get_autogen_tools
            
            # Get the autogen_tools module
            tools_module = _get_autogen_tools()
            if tools_module:
                # Register adapters based on the pattern in the original code
                for attr_name in dir(tools_module):
                    if attr_name.startswith('autogen_') and not attr_name.startswith('__'):
                        adapter = getattr(tools_module, attr_name)
                        if callable(adapter):
                            # Extract tool type name from adapter function name
                            # e.g., 'autogen_CodeDocsSearchTool' -> 'CodeDocsSearchTool'
                            tool_type_name = attr_name.replace('autogen_', '')
                            self.register_autogen_adapter(tool_type_name, adapter)
                            
        except ImportError as e:
            logger.warning(f"Could not register builtin AutoGen adapters: {e}")
        except Exception as e:
            logger.warning(f"Error registering builtin AutoGen adapters: {e}")
    
    def __len__(self) -> int:
        """Return total number of registered tools."""
        return len(self._functions) + len(self._autogen_adapters)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool function is registered."""
        return name in self._functions