"""Tool resolver for YAML-based tool name resolution.

This module provides the ToolResolver class that resolves tool names (strings)
from YAML files to actual callable functions/classes.

Resolution order (first match wins):
1. Local tools.py (backward compat, custom tools, custom variables)
2. praisonaiagents.tools.TOOL_MAPPINGS (built-in SDK tools)
3. praisonai-tools package (external tools, optional)
4. Tool registry (plugins via entry_points)

Usage:
    from praisonai.tool_resolver import ToolResolver, resolve_tool
    
    # Class-based
    resolver = ToolResolver()
    tool = resolver.resolve("tavily_search")
    tools = resolver.resolve_many(["tavily_search", "internet_search"])
    
    # Convenience functions
    tool = resolve_tool("tavily_search")
    tools = resolve_tools(["tavily_search", "internet_search"])
"""

import logging
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolResolver:
    """Resolves tool names to callables from multiple sources.
    
    Thread-safe and caches local tools.py to avoid repeated file reads.
    Supports custom tools via local tools.py while also providing access
    to built-in tools from praisonaiagents.tools.
    
    Attributes:
        _local_tools_cache: Cached tools from local tools.py
        _local_tools_loaded: Whether local tools have been loaded
    """
    
    def __init__(self, tools_py_path: Optional[str] = None):
        """Initialize the resolver.
        
        Args:
            tools_py_path: Optional path to tools.py. If None, uses ./tools.py
        """
        self._tools_py_path = tools_py_path or "tools.py"
        self._local_tools_cache: Dict[str, Callable] = {}
        self._local_tools_loaded: bool = False
        self._praisonai_tools_available: Optional[bool] = None
    
    def _load_local_tools(self) -> Dict[str, Callable]:
        """Load tools from local tools.py file.
        
        Returns:
            Dict mapping tool names to callables
        """
        if self._local_tools_loaded:
            return self._local_tools_cache
        
        self._local_tools_loaded = True
        
        tools_path = Path(self._tools_py_path)
        if not tools_path.exists():
            logger.debug(f"No local tools.py found at {tools_path}")
            return self._local_tools_cache
        
        try:
            spec = importlib.util.spec_from_file_location("tools", str(tools_path))
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for {tools_path}")
                return self._local_tools_cache
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Extract callable functions (not classes, not private)
            for name, obj in inspect.getmembers(module):
                if (not name.startswith('_') and 
                    callable(obj) and 
                    not inspect.isclass(obj)):
                    self._local_tools_cache[name] = obj
                    logger.debug(f"Loaded local tool: {name}")
            
            logger.info(f"Loaded {len(self._local_tools_cache)} tools from {tools_path}")
            
        except Exception as e:
            logger.warning(f"Error loading tools from {tools_path}: {e}")
        
        return self._local_tools_cache
    
    def _resolve_from_praisonaiagents(self, name: str) -> Optional[Callable]:
        """Resolve tool from praisonaiagents.tools.TOOL_MAPPINGS.
        
        Uses lazy loading via __getattr__ in praisonaiagents.tools.
        
        Args:
            name: Tool name to resolve
            
        Returns:
            Callable if found, None otherwise
        """
        try:
            from praisonaiagents import tools as agent_tools
            
            # Check if name is in TOOL_MAPPINGS
            if hasattr(agent_tools, 'TOOL_MAPPINGS'):
                if name in agent_tools.TOOL_MAPPINGS:
                    # Use __getattr__ to lazily load the tool
                    tool = getattr(agent_tools, name, None)
                    if tool is not None:
                        logger.debug(f"Resolved '{name}' from praisonaiagents.tools")
                        return tool
            
            # Also try direct attribute access (for non-TOOL_MAPPINGS items)
            tool = getattr(agent_tools, name, None)
            if tool is not None and callable(tool):
                logger.debug(f"Resolved '{name}' from praisonaiagents.tools (direct)")
                return tool
                
        except ImportError:
            logger.debug("praisonaiagents not available")
        except AttributeError:
            pass
        except Exception as e:
            logger.debug(f"Error resolving '{name}' from praisonaiagents: {e}")
        
        return None
    
    def _resolve_from_praisonai_tools(self, name: str) -> Optional[Callable]:
        """Resolve tool from praisonai-tools package (external).
        
        Args:
            name: Tool name to resolve
            
        Returns:
            Callable if found, None otherwise
        """
        # Cache availability check
        if self._praisonai_tools_available is None:
            self._praisonai_tools_available = importlib.util.find_spec("praisonai_tools") is not None
        
        if not self._praisonai_tools_available:
            return None
        
        try:
            import praisonai_tools
            
            # Try to get the tool via __getattr__ (lazy loading)
            tool = getattr(praisonai_tools, name, None)
            if tool is not None:
                logger.debug(f"Resolved '{name}' from praisonai-tools")
                return tool
                
        except ImportError:
            self._praisonai_tools_available = False
        except AttributeError:
            pass
        except Exception as e:
            logger.debug(f"Error resolving '{name}' from praisonai-tools: {e}")
        
        return None
    
    def _resolve_from_registry(self, name: str) -> Optional[Callable]:
        """Resolve tool from the global tool registry.
        
        Args:
            name: Tool name to resolve
            
        Returns:
            Callable if found, None otherwise
        """
        try:
            from praisonaiagents.tools.registry import get_tool
            tool = get_tool(name)
            if tool is not None:
                logger.debug(f"Resolved '{name}' from tool registry")
                return tool
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Error resolving '{name}' from registry: {e}")
        
        return None
    
    def resolve(self, name: str) -> Optional[Callable]:
        """Resolve a tool name to a callable.
        
        Resolution order:
        1. Local tools.py (backward compat, custom tools)
        2. praisonaiagents.tools.TOOL_MAPPINGS (built-in)
        3. praisonai-tools package (external, optional)
        4. Tool registry (plugins)
        
        Args:
            name: Tool name to resolve
            
        Returns:
            Callable if found, None if not found
        """
        if not name or not isinstance(name, str):
            return None
        
        name = name.strip()
        if not name:
            return None
        
        # 1. Check local tools.py first (highest priority)
        local_tools = self._load_local_tools()
        if name in local_tools:
            logger.debug(f"Resolved '{name}' from local tools.py")
            return local_tools[name]
        
        # 2. Check praisonaiagents.tools
        tool = self._resolve_from_praisonaiagents(name)
        if tool is not None:
            return tool
        
        # 3. Check praisonai-tools package
        tool = self._resolve_from_praisonai_tools(name)
        if tool is not None:
            return tool
        
        # 4. Check tool registry
        tool = self._resolve_from_registry(name)
        if tool is not None:
            return tool
        
        logger.warning(f"Tool '{name}' not found in any source")
        return None
    
    def resolve_many(self, names: List[str]) -> List[Callable]:
        """Resolve multiple tool names to callables.
        
        Skips missing tools with a warning instead of failing.
        
        Args:
            names: List of tool names to resolve
            
        Returns:
            List of resolved callables (may be shorter than input if some missing)
        """
        if not names:
            return []
        
        tools = []
        for name in names:
            tool = self.resolve(name)
            if tool is not None:
                tools.append(tool)
            else:
                logger.warning(f"Skipping unresolved tool: '{name}'")
        
        return tools
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool name can be resolved.
        
        Args:
            name: Tool name to check
            
        Returns:
            True if tool exists, False otherwise
        """
        return self.resolve(name) is not None
    
    def list_available(self) -> Dict[str, str]:
        """List all available tools with descriptions.
        
        Returns:
            Dict mapping tool names to descriptions
        """
        available: Dict[str, str] = {}
        
        # 1. Add local tools
        local_tools = self._load_local_tools()
        for name, tool in local_tools.items():
            doc = getattr(tool, '__doc__', None) or f"Local tool: {name}"
            available[name] = doc.split('\n')[0].strip()  # First line only
        
        # 2. Add praisonaiagents.tools
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            for name in TOOL_MAPPINGS.keys():
                if name not in available:
                    available[name] = "Built-in tool from praisonaiagents"
        except ImportError:
            pass
        
        # 3. Add praisonai-tools (if installed)
        if self._praisonai_tools_available is None:
            self._praisonai_tools_available = importlib.util.find_spec("praisonai_tools") is not None
        
        if self._praisonai_tools_available:
            try:
                from praisonai_tools import __all__ as praisonai_tools_all
                for name in praisonai_tools_all:
                    if name not in available:
                        available[name] = "External tool from praisonai-tools"
            except (ImportError, AttributeError):
                pass
        
        return available
    
    def validate_yaml_tools(self, yaml_config: Dict[str, Any]) -> List[str]:
        """Validate that all tools referenced in YAML config can be resolved.
        
        Args:
            yaml_config: Parsed YAML configuration dict
            
        Returns:
            List of tool names that could not be resolved (empty if all valid)
        """
        missing = []
        
        roles = yaml_config.get('roles', {})
        # Also support 'agents' key for canonical format
        if not roles:
            roles = yaml_config.get('agents', {})
        
        for role_name, role_config in roles.items():
            if not isinstance(role_config, dict):
                continue
            
            tools = role_config.get('tools', [])
            if not tools:
                continue
            
            for tool_name in tools:
                if not tool_name or not isinstance(tool_name, str):
                    continue
                if not self.has_tool(tool_name.strip()):
                    missing.append(tool_name)
        
        return list(set(missing))  # Remove duplicates
    
    def clear_cache(self) -> None:
        """Clear the local tools cache.
        
        Useful when tools.py has been modified and needs to be reloaded.
        """
        self._local_tools_cache.clear()
        self._local_tools_loaded = False


# Global resolver instance (lazy initialized)
_global_resolver: Optional[ToolResolver] = None


def _get_resolver() -> ToolResolver:
    """Get or create the global resolver instance."""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = ToolResolver()
    return _global_resolver


# Convenience functions
def resolve_tool(name: str) -> Optional[Callable]:
    """Resolve a tool name to a callable.
    
    Args:
        name: Tool name to resolve
        
    Returns:
        Callable if found, None otherwise
    """
    return _get_resolver().resolve(name)


def resolve_tools(names: List[str]) -> List[Callable]:
    """Resolve multiple tool names to callables.
    
    Args:
        names: List of tool names
        
    Returns:
        List of resolved callables
    """
    return _get_resolver().resolve_many(names)


def list_available_tools() -> Dict[str, str]:
    """List all available tools with descriptions.
    
    Returns:
        Dict mapping tool names to descriptions
    """
    return _get_resolver().list_available()


def has_tool(name: str) -> bool:
    """Check if a tool name can be resolved.
    
    Args:
        name: Tool name to check
        
    Returns:
        True if tool exists, False otherwise
    """
    return _get_resolver().has_tool(name)


def validate_yaml_tools(yaml_config: Dict[str, Any]) -> List[str]:
    """Validate that all tools in YAML config can be resolved.
    
    Args:
        yaml_config: Parsed YAML configuration
        
    Returns:
        List of missing tool names
    """
    return _get_resolver().validate_yaml_tools(yaml_config)
