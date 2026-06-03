"""Tool registry for managing and discovering tools.

This module provides centralized tool management with support for:
- Manual registration
- Auto-discovery via entry_points
- Tool lookup by name
- Thread-safe operations for multi-agent scenarios

Usage:
    from praisonaiagents.tools.registry import get_registry
    
    registry = get_registry()
    registry.register(my_tool)
    tool = registry.get("my_tool")
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass

from .base import BaseTool

# Lazy load entry_points to reduce import time
_entry_points = None

def _get_entry_points():
    """Lazy load entry_points from importlib.metadata."""
    global _entry_points
    if _entry_points is None:
        from importlib.metadata import entry_points as _ep
        _entry_points = _ep
    return _entry_points


# Entry point group name for external plugins
ENTRY_POINT_GROUP = "praisonaiagents.tools"


@dataclass
class ToolEntry:
    """Internal registry entry for a tool with optional dynamic schema override."""
    tool: Union[BaseTool, Callable]
    schema_override: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    available: bool = True
    
    @property
    def name(self) -> str:
        """Get the tool name."""
        if hasattr(self.tool, 'name'):
            return self.tool.name
        elif hasattr(self.tool, '__name__'):
            return self.tool.__name__
        else:
            return str(id(self.tool))
    
    @property
    def schema(self) -> Dict[str, Any]:
        """Get the tool schema, applying dynamic overrides if present."""
        # Get base schema
        if hasattr(self.tool, 'get_schema'):
            # If the tool already handles schema overrides (like FunctionTool), 
            # just use its get_schema() method and don't apply override again
            return self.tool.get_schema()
        else:
            # For plain functions, generate schema and apply override if present
            from .decorator import get_tool_schema
            base_schema = get_tool_schema(self.tool)
            
            # Apply dynamic override if present
            if self.schema_override is not None:
                try:
                    return self.schema_override(base_schema)
                except Exception as e:
                    logging.warning(f"Dynamic schema override failed for tool '{self.name}': {e}")
                    return base_schema
            
            return base_schema


class ToolRegistry:
    """Central registry for all tools.
    
    Provides:
    - Tool registration (manual and auto-discovery)
    - Tool lookup by name
    - Tool listing and filtering
    - Entry points discovery for external plugins
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}  # Unified storage for tools and functions
        self._discovered: bool = False
        self._lock = threading.RLock()  # Thread-safe operations for multi-agent scenarios
    
    def register(
        self,
        tool: Union[BaseTool, Callable],
        name: Optional[str] = None,
        overwrite: bool = False,
        dynamic_schema_overrides: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    ) -> None:
        """Register a tool with the registry.
        
        Thread-safe: Uses lock for concurrent access in multi-agent scenarios.
        
        Args:
            tool: BaseTool instance or callable function
            name: Override name (default: tool.name or function.__name__)
            overwrite: If True, overwrite existing tool with same name
            dynamic_schema_overrides: Optional function to dynamically modify tool schema.
                Called with base schema dict, returns modified schema dict.
        
        Raises:
            ValueError: If tool with same name exists and overwrite=False
        """
        with self._lock:
            # Determine tool name
            if isinstance(tool, BaseTool):
                tool_name = name or tool.name
            elif callable(tool):
                tool_name = name or getattr(tool, '__name__', str(id(tool)))
            else:
                raise TypeError(f"Cannot register {type(tool)}, expected BaseTool or callable")
            
            # Check for existing tool
            if tool_name in self._tools and not overwrite:
                logging.debug(f"Tool '{tool_name}' already registered, skipping")
                return
            
            # Create tool entry with optional dynamic override
            entry = ToolEntry(
                tool=tool,
                schema_override=dynamic_schema_overrides,
                available=True
            )
            
            self._tools[tool_name] = entry
            logging.debug(f"Registered tool: {tool_name}")
            if dynamic_schema_overrides:
                logging.debug(f"Tool '{tool_name}' has dynamic schema override function")
    
    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.
        
        Thread-safe: Uses lock for concurrent access.
        
        Args:
            name: Tool name to remove
            
        Returns:
            True if tool was removed, False if not found
        """
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                return True
            return False
    
    def get(self, name: str) -> Optional[Union[BaseTool, Callable]]:
        """Get a tool by name.
        
        Thread-safe: Uses lock for concurrent access.
        
        Args:
            name: Tool name
            
        Returns:
            BaseTool instance, callable, or None if not found
        """
        with self._lock:
            # Check tool registry first
            if name in self._tools:
                return self._tools[name].tool
            
            # Try auto-discovery if not found
            if not self._discovered:
                self.discover_plugins()
                if name in self._tools:
                    return self._tools[name].tool
            
            return None
    
    def list_tools(self) -> List[str]:
        """List all registered tool names. Thread-safe."""
        with self._lock:
            return list(self._tools.keys())
    
    def list_base_tools(self) -> List[BaseTool]:
        """List all registered BaseTool instances. Thread-safe."""
        with self._lock:
            base_tools = []
            for entry in self._tools.values():
                if isinstance(entry.tool, BaseTool):
                    base_tools.append(entry.tool)
            return base_tools
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions with dynamic schema overrides applied.
        
        This is the main entry point for getting tool schemas that respects
        dynamic overrides. Called every time tools need to be passed to the LLM.
        
        Returns:
            List of OpenAI-compatible tool definition dictionaries
        """
        with self._lock:
            definitions = []
            for entry in self._tools.values():
                if not entry.available:
                    continue
                
                # Check tool availability if it supports the protocol
                if hasattr(entry.tool, 'check_availability'):
                    try:
                        is_available, reason = entry.tool.check_availability()
                        if not is_available:
                            if reason:
                                logging.debug(f"Tool '{entry.name}' unavailable: {reason}")
                            continue
                    except Exception as e:
                        logging.warning(f"Availability check failed for tool '{entry.name}': {e}")
                        continue
                
                # Get schema with dynamic overrides applied
                try:
                    schema = entry.schema
                    definitions.append(schema)
                except Exception as e:
                    logging.error(f"Failed to get schema for tool '{entry.name}': {e}")
                    continue
            
            return definitions
    
    def list_available_tools(self, context: Optional[Dict[str, Any]] = None) -> List[Union[BaseTool, Callable]]:
        """List only currently available tools (those that pass availability checks).
        
        Args:
            context: Optional context for availability checks (unused currently)
            
        Returns:
            List of available tools (both BaseTool instances and callables)
        """
        with self._lock:
            available = []
            
            for entry in self._tools.values():
                if not entry.available:
                    continue
                
                # Check if tool has availability checking capability
                if hasattr(entry.tool, 'check_availability'):
                    try:
                        is_available, reason = entry.tool.check_availability()
                        if is_available:
                            available.append(entry.tool)
                        elif reason:
                            logging.debug(f"Tool '{entry.name}' unavailable: {reason}")
                    except Exception as e:
                        logging.warning(f"Availability check failed for tool '{entry.name}': {e}")
                else:
                    # No availability check = always available
                    available.append(entry.tool)
            
            return available
    
    def list_tools_with_allowed_filter(self, context: Optional[Dict[str, Any]] = None) -> List[str]:
        """List tool names filtered by ALLOWED_TOOLS environment variable.
        
        This applies the canonical ALLOWED_TOOLS filter to prevent tool
        name collisions in multi-environment agent systems.
        
        Args:
            context: Optional context for availability checks
            
        Returns:
            List of filtered tool names
        """
        try:
            # Lazy import to avoid circular dependencies
            from ..allowed_tools_filter import filter_tools_with_allowed_tools
            
            # Get all available tool names
            all_tools = self.list_tools()
            
            # Apply ALLOWED_TOOLS filter with diagnostics
            filtered_tools = filter_tools_with_allowed_tools(all_tools, log_diagnostics=True)
            
            return sorted(filtered_tools)
            
        except ImportError:
            logging.warning("ALLOWED_TOOLS filter not available, returning all tools")
            return self.list_tools()
        except ValueError:
            # Preserve strict ALLOWED_TOOLS semantics (e.g., CI unknown tools, empty value)
            raise
        except Exception as e:
            logging.error("Error applying ALLOWED_TOOLS filter: %s", e)
            # Fallback to all tools on error
            return self.list_tools()
    
    def get_all(self) -> Dict[str, Union[BaseTool, Callable]]:
        """Get all registered tools as a dict. Thread-safe."""
        with self._lock:
            result = {}
            for name, entry in self._tools.items():
                result[name] = entry.tool
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
            eps = _get_entry_points()(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Python 3.9 fallback
            try:
                all_eps = _get_entry_points()()
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
    
    def discover_single_file_plugins(self) -> int:
        """Discover and load tools from single-file plugins.
        
        Scans default plugin directories for WordPress-style plugins:
        - ./.praisonai/plugins/ (project-level)
        - ~/.praisonai/plugins/ (user-level)
        
        Returns:
            Number of plugins loaded
        """
        try:
            from ..plugins.discovery import discover_and_load_plugins
            loaded = discover_and_load_plugins(plugin_dirs=None, include_defaults=True)
            return len(loaded)
        except ImportError:
            logging.debug("Plugin discovery module not available")
            return 0
        except Exception as e:
            logging.warning(f"Error discovering single-file plugins: {e}")
            return 0
    
    def clear(self) -> None:
        """Clear all registered tools. Thread-safe."""
        with self._lock:
            self._tools.clear()
            self._discovered = False
    
    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._tools
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)
    
    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self._tools)})"


# Global registry instance (protected by _registry_lock for thread safety)
_registry_lock = threading.Lock()
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance. Thread-safe singleton."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            # Double-checked locking pattern
            if _global_registry is None:
                _global_registry = ToolRegistry()
    return _global_registry


def register_tool(
    tool: Union[BaseTool, Callable],
    name: Optional[str] = None,
    dynamic_schema_overrides: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> None:
    """Convenience function to register a tool with the global registry."""
    get_registry().register(tool, name=name, dynamic_schema_overrides=dynamic_schema_overrides)


def get_tool(name: str) -> Optional[Union[BaseTool, Callable]]:
    """Convenience function to get a tool from the global registry."""
    return get_registry().get(name)


# Simplified alias for register_tool
def add_tool(
    tool: Union[BaseTool, Callable],
    name: Optional[str] = None,
    dynamic_schema_overrides: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> None:
    """Register a tool. Simplified alias for register_tool().
    
    Args:
        tool: BaseTool instance or callable function
        name: Optional override name
        dynamic_schema_overrides: Optional function to dynamically modify tool schema
    """
    register_tool(tool, name=name, dynamic_schema_overrides=dynamic_schema_overrides)


def has_tool(name: str) -> bool:
    """Check if a tool is registered in the global registry.
    
    Args:
        name: Name of the tool to check
        
    Returns:
        True if tool exists, False otherwise
    """
    return get_registry().get(name) is not None


def remove_tool(name: str) -> bool:
    """Remove a tool from the global registry.
    
    Args:
        name: Name of the tool to remove
        
    Returns:
        True if tool was found and removed, False otherwise
    """
    return get_registry().unregister(name)


def list_tools() -> List[str]:
    """List all registered tool names.
    
    Returns:
        List of tool names
    """
    return get_registry().list_tools()


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get OpenAI-compatible tool definitions with dynamic schema overrides applied.
    
    This is the main entry point for getting tool schemas that respects
    dynamic overrides. Called every time tools need to be passed to the LLM.
    
    Returns:
        List of OpenAI-compatible tool definition dictionaries
    """
    return get_registry().get_tool_definitions()


def discover_plugins() -> int:
    """Discover and load tools from single-file plugins.
    
    Scans default plugin directories for WordPress-style plugins:
    - ./.praisonai/plugins/ (project-level)
    - ~/.praisonai/plugins/ (user-level)
    
    Returns:
        Number of plugins loaded
    """
    return get_registry().discover_single_file_plugins()


def list_available_tools(context: Optional[Dict[str, Any]] = None) -> List[Union[BaseTool, Callable]]:
    """List only currently available tools from the global registry.
    
    Args:
        context: Optional context for availability checks
        
    Returns:
        List of available tools
    """
    return get_registry().list_available_tools(context)


def list_tools_with_allowed_filter(context: Optional[Dict[str, Any]] = None) -> List[str]:
    """List tool names filtered by ALLOWED_TOOLS from the global registry.
    
    This is the canonical entry point for applying ALLOWED_TOOLS filtering
    across the PraisonAI ecosystem.
    
    Args:
        context: Optional context for availability checks
        
    Returns:
        List of filtered tool names
    """
    return get_registry().list_tools_with_allowed_filter(context)


# Backward compatibility alias
def list_tools_with_hermes_filter(context: Optional[Dict[str, Any]] = None) -> List[str]:
    """Backward compatibility alias for list_tools_with_allowed_filter."""
    return list_tools_with_allowed_filter(context)
