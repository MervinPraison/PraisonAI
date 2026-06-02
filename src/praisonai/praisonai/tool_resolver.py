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
import os
import importlib.util
import inspect
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from types import MappingProxyType
from ._safe_loader import load_user_module

logger = logging.getLogger(__name__)

# Sentinel for cache - needed because None is a valid cached result (tool not found)
_SENTINEL = object()


class ToolResolver:
    """Resolves tool names to callables from multiple sources.
    
    Thread-safe and caches local tools.py to avoid repeated file reads.
    Supports custom tools via local tools.py while also providing access
    to built-in tools from praisonaiagents.tools.
    
    Attributes:
        _local_tools_cache: Cached tools from local tools.py
        _local_tools_loaded: Whether local tools have been loaded
        _registry: Optional ToolRegistry for wrapper-level tool registration
        _resolve_cache: Cached results from resolve() calls
        _resolve_cache_lock: Thread lock for resolve cache
    """
    
    def __init__(
        self,
        tools_py_path: Optional[str] = None,
        registry: Optional["ToolRegistry"] = None,
    ):
        """Initialize the resolver.
        
        Args:
            tools_py_path: Optional path to tools.py. If None, uses ./tools.py
            registry: Optional ToolRegistry to include in resolution chain
        """
        from pathlib import Path
        # Resolve path eagerly in constructor to make binding explicit and inspectable
        self._tools_py_path = str(Path(tools_py_path or "tools.py").resolve())
        self._local_tools_cache: Mapping[str, Callable] = MappingProxyType({})
        self._local_tools_loaded: bool = False
        self._praisonai_tools_available: Optional[bool] = None
        self._local_tools_lock = threading.Lock()
        self._registry = registry
        
        # Cache for resolved tools to avoid repeated resolution
        self._resolve_cache: Dict[str, Optional[Callable]] = {}
        self._resolve_cache_lock = threading.Lock()
    
    def _load_local_tools(self) -> Mapping[str, Callable]:
        """Load tools from local tools.py file.
        
        Security: Requires PRAISONAI_ALLOW_LOCAL_TOOLS=true to prevent
        arbitrary code execution from untrusted working directories.
        
        Returns:
            Immutable dict mapping tool names to callables
        """
        if self._local_tools_loaded:
            return self._local_tools_cache
        
        with self._local_tools_lock:
            if self._local_tools_loaded:  # Double-check inside lock
                return self._local_tools_cache
            
            tools_path = Path(self._tools_py_path)
            try:
                # Use the same safe loader as other tools.py loading paths
                module = load_user_module(self._tools_py_path, name="tools")
                if module is None:
                    logger.debug(f"Local tools loading disabled or tools.py not found at {self._tools_py_path}")
                    self._local_tools_cache = MappingProxyType({})
                    self._local_tools_loaded = True
                    return self._local_tools_cache
                
                # Build cache locally, then freeze
                cache: Dict[str, Callable] = {}
                for name, obj in inspect.getmembers(module):
                    if (not name.startswith('_') and 
                        callable(obj) and 
                        not inspect.isclass(obj)):
                        cache[name] = obj
                        logger.debug(f"Loaded local tool: {name}")
                
                logger.info(f"Loaded {len(cache)} tools from {self._tools_py_path}")
                
                # Create immutable view to prevent concurrent modification
                self._local_tools_cache = MappingProxyType(cache)
                
            except Exception as e:
                logger.warning(f"Error loading tools from {self._tools_py_path}: {e}")
                self._local_tools_cache = MappingProxyType({})
            
            self._local_tools_loaded = True
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
                    try:
                        tool = getattr(agent_tools, name)
                    except Exception as e:
                        # Tool exists in TOOL_MAPPINGS but failed to load
                        # (e.g. missing dependency like psutil)
                        logger.warning(
                            f"Tool '{name}' exists in TOOL_MAPPINGS but failed to load: {e}"
                        )
                        return None
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
            from ._framework_availability import is_available
            self._praisonai_tools_available = is_available("praisonai_tools")
        
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
    
    def _resolve_from_wrapper_registry(self, name: str) -> Optional[Callable]:
        """Resolve tool from the wrapper ToolRegistry.
        
        Args:
            name: Tool name to resolve
            
        Returns:
            Callable if found, None otherwise
        """
        if self._registry is None:
            return None
        
        tool = self._registry.get_function(name)
        if tool is not None:
            logger.debug(f"Resolved '{name}' from wrapper ToolRegistry")
            return tool
        
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
        2. Wrapper ToolRegistry (register_function API)
        3. praisonaiagents.tools.TOOL_MAPPINGS (built-in)
        4. praisonai-tools package (external, optional)
        5. Core SDK tool registry (plugins)
        
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

        # Fast path: cached result
        cached = self._resolve_cache.get(name, _SENTINEL)
        if cached is not _SENTINEL:
            return cached

        # Load local tools outside the cache lock to prevent lock-order inversion
        local_tools = self._load_local_tools()

        with self._resolve_cache_lock:
            # Double-check inside lock
            cached = self._resolve_cache.get(name, _SENTINEL)
            if cached is not _SENTINEL:
                return cached

            # 1. Check local tools.py first (highest priority)
            if name in local_tools:
                logger.debug(f"Resolved '{name}' from local tools.py")
                tool = local_tools[name]
                self._resolve_cache[name] = tool
                return tool
            
            # 2. Check wrapper ToolRegistry (NEW - ahead of SDK paths)
            tool = self._resolve_from_wrapper_registry(name)
            if tool is not None:
                self._resolve_cache[name] = tool
                return tool
            
            # 3. Check praisonaiagents.tools
            tool = self._resolve_from_praisonaiagents(name)
            if tool is not None:
                self._resolve_cache[name] = tool
                return tool
            
            # 4. Check praisonai-tools package
            tool = self._resolve_from_praisonai_tools(name)
            if tool is not None:
                self._resolve_cache[name] = tool
                return tool
            
            # 5. Check core SDK tool registry
            tool = self._resolve_from_registry(name)
            if tool is not None:
                self._resolve_cache[name] = tool
                return tool
            
            # Cache the None result to avoid repeated failed lookups
            logger.warning(f"Tool '{name}' not found in any source")
            self._resolve_cache[name] = None
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
            from ._framework_availability import is_available
            self._praisonai_tools_available = is_available("praisonai_tools")
        
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
        """Clear both the local tools cache and resolve cache.
        
        Useful when tools.py has been modified and needs to be reloaded.
        """
        with self._local_tools_lock:
            self._local_tools_cache = MappingProxyType({})
            self._local_tools_loaded = False
        with self._resolve_cache_lock:
            self._resolve_cache.clear()
    
    def get_local_callables(self) -> List[Callable]:
        """Get functions exposed by tools.py (path A semantics).
        
        Returns:
            List of callable functions from tools.py
        """
        local_tools = self._load_local_tools()
        return list(local_tools.values())
    
    def get_local_tool_classes(self) -> Dict[str, Any]:
        """Get BaseTool/langchain class instances from tools.py (path B semantics).
        
        Returns:
            Dictionary mapping class names to instantiated tool objects
        """
        try:
            # Use the same safe loader to get the module
            module = load_user_module(self._tools_py_path, name="tools_module")
            if module is None:
                return {}
            return self._extract_tool_classes(module)
        except Exception as e:
            logger.warning(f"Error loading tool classes from {self._tools_py_path}: {e}")
            return {}

    def get_local_tool_classes_from_dir(self, tools_dir: "os.PathLike|str") -> Dict[str, Any]:
        """Load BaseTool/langchain classes from every *.py in a tools/ directory.
        
        Args:
            tools_dir: Path to the tools directory
            
        Returns:
            Dictionary mapping class names to instantiated tool objects
        """
        from pathlib import Path
        from ._safe_loader import load_user_module
        
        classes: Dict[str, Any] = {}
        for py_file in Path(tools_dir).glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            try:
                module = load_user_module(py_file, name=f"tools_{py_file.stem}")
                if module is not None:
                    classes.update(self._extract_tool_classes(module))
            except Exception as e:
                logger.warning(f"Error loading tool classes from file {py_file}: {e}")
        return classes

    def _extract_tool_classes(self, module):
        """Extract tool classes from a loaded module that inherit from BaseTool 
        or are part of langchain_community.tools package.
        """
        # Import the necessary classes (matching agents_generator.py logic)
        BaseTool = None
        PRAISONAI_TOOLS_AVAILABLE = False
        try:
            from praisonai_tools import BaseTool
            PRAISONAI_TOOLS_AVAILABLE = True
        except ImportError:
            try:
                from praisonai.tools import BaseTool
                PRAISONAI_TOOLS_AVAILABLE = True
            except ImportError:
                pass
        
        result = {}
        for name, obj in inspect.getmembers(module, 
            lambda x: inspect.isclass(x) and (
                x.__module__.startswith('langchain_community.tools') or 
                (PRAISONAI_TOOLS_AVAILABLE and BaseTool and issubclass(x, BaseTool))
            ) and x is not BaseTool):
            try:
                result[name] = obj()
                logger.debug(f"Loaded tool class: {name}")
            except Exception as e:
                logger.warning(f"Error instantiating tool class {name}: {e}")
                continue
        
        return result


# Context-local resolver for multi-project safety
import contextvars

_resolver_var: contextvars.ContextVar[Optional[ToolResolver]] = contextvars.ContextVar(
    "tool_resolver", default=None,
)

def _get_default_resolver() -> ToolResolver:
    """Per-context resolver. Falls back to a fresh ToolResolver per context,
    so changing CWD between agents / requests is honoured.
    
    Each context (agent/task/request) gets its own resolver anchored to the
    working directory at the time of first use in that context. This prevents
    the singleton bug where the first caller locks in their CWD for the entire process.
    
    For test isolation or multi-project CLIs, create explicit resolver
    instances instead of using this cached default.
    """
    resolver = _resolver_var.get()
    if resolver is None:
        resolver = ToolResolver()
        _resolver_var.set(resolver)
    return resolver

def reset_default_resolver() -> None:
    """Explicit invalidation hook for daemons / IDE plugins switching projects.
    
    Call this when changing working directories or switching between projects
    to ensure the next tool resolution uses the new CWD.
    """
    _resolver_var.set(None)


# Convenience functions that use cached default resolver for performance
def resolve_tool(name: str, resolver: Optional[ToolResolver] = None) -> Optional[Callable]:
    """Resolve a tool name to a callable.
    
    Args:
        name: Tool name to resolve
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        Callable if found, None otherwise
        
    Note:
        When resolver=None, uses a context-local cached resolver anchored to the
        working directory for that context. For test isolation or multi-project
        CLIs, pass an explicit resolver instance.
    """
    return (resolver or _get_default_resolver()).resolve(name)


def resolve_tools(names: List[str], resolver: Optional[ToolResolver] = None) -> List[Callable]:
    """Resolve multiple tool names to callables.
    
    Args:
        names: List of tool names
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        List of resolved callables
    """
    return (resolver or _get_default_resolver()).resolve_many(names)


def list_available_tools(resolver: Optional[ToolResolver] = None) -> Dict[str, str]:
    """List all available tools with descriptions.
    
    Args:
        resolver: Optional resolver instance. If None, uses cached default resolver.
    
    Returns:
        Dict mapping tool names to descriptions
    """
    return (resolver or _get_default_resolver()).list_available()


def has_tool(name: str, resolver: Optional[ToolResolver] = None) -> bool:
    """Check if a tool name can be resolved.
    
    Args:
        name: Tool name to check
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        True if tool exists, False otherwise
    """
    return (resolver or _get_default_resolver()).has_tool(name)


def validate_yaml_tools(yaml_config: Dict[str, Any], resolver: Optional[ToolResolver] = None) -> List[str]:
    """Validate that all tools in YAML config can be resolved.
    
    Args:
        yaml_config: Parsed YAML configuration
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        List of missing tool names
    """
    return (resolver or _get_default_resolver()).validate_yaml_tools(yaml_config)


