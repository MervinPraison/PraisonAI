"""Tool registry for managing and discovering tools.

This module provides centralized tool management with support for:
- Manual registration
- Auto-discovery via entry_points
- Tool lookup by name

Usage:
    from praisonaiagents.tools.registry import get_registry
    
    registry = get_registry()
    registry.register(my_tool)
    tool = registry.get("my_tool")
"""

import logging
from typing import Callable, Dict, List, Optional, Union
from importlib.metadata import entry_points

from .base import BaseTool


# Entry point group name for external plugins
ENTRY_POINT_GROUP = "praisonaiagents.tools"


class ToolRegistry:
    """Central registry for all tools.
    
    Provides:
    - Tool registration (manual and auto-discovery)
    - Tool lookup by name
    - Tool listing and filtering
    - Entry points discovery for external plugins
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._functions: Dict[str, Callable] = {}  # For backward compat with plain functions
        self._discovered: bool = False
    
    def register(
        self,
        tool: Union[BaseTool, Callable],
        name: Optional[str] = None,
        overwrite: bool = False
    ) -> None:
        """Register a tool with the registry.
        
        Args:
            tool: BaseTool instance or callable function
            name: Override name (default: tool.name or function.__name__)
            overwrite: If True, overwrite existing tool with same name
        
        Raises:
            ValueError: If tool with same name exists and overwrite=False
        """
        # Handle BaseTool instances
        if isinstance(tool, BaseTool):
            tool_name = name or tool.name
            if tool_name in self._tools and not overwrite:
                logging.debug(f"Tool '{tool_name}' already registered, skipping")
                return
            self._tools[tool_name] = tool
            logging.debug(f"Registered tool: {tool_name}")
            return
        
        # Handle plain callables
        if callable(tool):
            tool_name = name or getattr(tool, '__name__', str(id(tool)))
            if tool_name in self._functions and not overwrite:
                logging.debug(f"Function '{tool_name}' already registered, skipping")
                return
            self._functions[tool_name] = tool
            logging.debug(f"Registered function: {tool_name}")
            return
        
        raise TypeError(f"Cannot register {type(tool)}, expected BaseTool or callable")
    
    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.
        
        Args:
            name: Tool name to remove
            
        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        if name in self._functions:
            del self._functions[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Union[BaseTool, Callable]]:
        """Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            BaseTool instance, callable, or None if not found
        """
        # Check BaseTool registry first
        if name in self._tools:
            return self._tools[name]
        
        # Check functions registry
        if name in self._functions:
            return self._functions[name]
        
        # Try auto-discovery if not found
        if not self._discovered:
            self.discover_plugins()
            if name in self._tools:
                return self._tools[name]
        
        return None
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys()) + list(self._functions.keys())
    
    def list_base_tools(self) -> List[BaseTool]:
        """List all registered BaseTool instances."""
        return list(self._tools.values())
    
    def get_all(self) -> Dict[str, Union[BaseTool, Callable]]:
        """Get all registered tools as a dict."""
        result = dict(self._tools)
        result.update(self._functions)
        return result
    
    def discover_plugins(self) -> int:
        """Discover and register tools from entry_points.
        
        External packages can register tools by adding to pyproject.toml:
        
            [project.entry-points."praisonaiagents.tools"]
            my_tool = "my_package.tools:MyTool"
        
        Returns:
            Number of tools discovered
        """
        if self._discovered:
            return 0
        
        count = 0
        try:
            # Python 3.10+ style
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Python 3.9 fallback
            try:
                all_eps = entry_points()
                eps = all_eps.get(ENTRY_POINT_GROUP, [])
            except Exception:
                eps = []
        
        for ep in eps:
            try:
                tool_class_or_func = ep.load()
                
                # If it's a class, instantiate it
                if isinstance(tool_class_or_func, type) and issubclass(tool_class_or_func, BaseTool):
                    tool_instance = tool_class_or_func()
                    self.register(tool_instance, name=ep.name)
                # If it's already an instance or callable
                elif isinstance(tool_class_or_func, BaseTool):
                    self.register(tool_class_or_func, name=ep.name)
                elif callable(tool_class_or_func):
                    self.register(tool_class_or_func, name=ep.name)
                else:
                    logging.warning(f"Entry point '{ep.name}' is not a valid tool")
                    continue
                
                count += 1
                logging.info(f"Discovered plugin tool: {ep.name}")
            except Exception as e:
                logging.warning(f"Failed to load plugin '{ep.name}': {e}")
        
        self._discovered = True
        return count
    
    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._functions.clear()
        self._discovered = False
    
    def __contains__(self, name: str) -> bool:
        return name in self._tools or name in self._functions
    
    def __len__(self) -> int:
        return len(self._tools) + len(self._functions)
    
    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self._tools)}, functions={len(self._functions)})"


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(
    tool: Union[BaseTool, Callable],
    name: Optional[str] = None
) -> None:
    """Convenience function to register a tool with the global registry."""
    get_registry().register(tool, name=name)


def get_tool(name: str) -> Optional[Union[BaseTool, Callable]]:
    """Convenience function to get a tool from the global registry."""
    return get_registry().get(name)
