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
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol
from types import MappingProxyType
from ._safe_loader import load_user_module

logger = logging.getLogger(__name__)


class _ResolveResult:
    """Internal result wrapper to distinguish cacheable vs non-cacheable failures."""
    __slots__ = ("tool", "cacheable")

    def __init__(self, tool, cacheable=True):
        self.tool = tool
        self.cacheable = cacheable


# Sentinel for cache - needed because None is a valid cached result (tool not found)
_SENTINEL = object()


class ToolSource(Protocol):
    """Protocol for anything that can provide tools."""
    @property
    def name(self) -> str:
        """Name identifying this source for debugging."""
        ...
    
    def lookup(self, name: str) -> Optional[Callable]:
        """Look up a tool by name, returning None if not found.

        May also return a :class:`_ResolveResult` to signal whether a negative
        (None) result is safe to cache. Returning a bare callable (or None) is
        treated as a cacheable result.
        """
        ...


class _CallableSource:
    """Adapts a bound ``_resolve_from_*`` method into a :class:`ToolSource`.

    The wrapped callable may return either a plain callable / None, or a
    :class:`_ResolveResult`. Either is forwarded unchanged so the existing
    cacheable / non-cacheable semantics are preserved.
    """
    __slots__ = ("name", "_fn")

    def __init__(self, name: str, fn: Callable[[str], Any]):
        self.name = name
        self._fn = fn

    def lookup(self, name: str):
        return self._fn(name)


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
        sources: Optional[List[ToolSource]] = None,
    ):
        """Initialize the resolver.
        
        Args:
            tools_py_path: Optional path to tools.py. If None, uses ./tools.py
            registry: Optional ToolRegistry to include in resolution chain
            sources: Optional list of ToolSource objects. If None, uses defaults.
        """
        from pathlib import Path
        # Resolve path eagerly in constructor to make binding explicit and inspectable
        self._tools_py_path = str(Path(tools_py_path or "tools.py").resolve())
        self._local_tools_cache: Mapping[str, Callable] = MappingProxyType({})
        self._local_tools_loaded: bool = False
        self._praisonai_tools_available: Optional[bool] = None
        self._local_tools_lock = threading.Lock()
        self._registry = registry
        
        # Resolution chain as an ordered list of ToolSource objects. When a
        # caller supplies sources= they fully control resolution order; this is
        # the documented extension point. Otherwise we build the default chain
        # equivalent to the historical hardcoded order.
        if sources is not None:
            self._sources: List[ToolSource] = list(sources)
        else:
            self._sources = self.default_sources(registry)

        # Auto-wire cache invalidation so register_function() on the registry
        # invalidates this resolver's cache without the caller having to
        # remember registry.set_resolver(resolver).
        if registry is not None:
            try:
                registry.set_resolver(self)
            except Exception:  # pragma: no cover - defensive, registry is duck-typed
                logger.debug("Could not auto-wire resolver into registry", exc_info=True)
        
        # Cache for resolved tools to avoid repeated resolution
        self._resolve_cache: Dict[str, Optional[Callable]] = {}
        self._resolve_cache_lock = threading.Lock()
        # Monotonic version bumped on every invalidate/clear so an in-flight
        # resolve() (which runs source lookups OUTSIDE the lock) can detect a
        # concurrent invalidation and skip writing a now-stale result.
        self._resolve_cache_epoch = 0

    def default_sources(self, registry: Optional["ToolRegistry"] = None) -> List[ToolSource]:
        """Build the default resolution chain as a list of ToolSource objects.

        Equivalent to the historical hardcoded order:

        1. Local ``tools.py`` (highest priority)
        2. Wrapper ``ToolRegistry`` (register_function API)
        3. ``praisonaiagents.tools`` (built-in SDK tools)
        4. ``praisonai-tools`` package (external, optional)
        5. Core SDK tool registry (plugins)

        Exposed so callers can compose around the defaults, e.g.::

            ToolResolver(sources=[*custom, *resolver.default_sources(registry)])
        """
        def _local_lookup(name: str):
            local_tools = self._load_local_tools()
            tool = local_tools.get(name)
            return _ResolveResult(tool) if tool is not None else None

        # Dispatch through ``self`` at call time (rather than binding the method
        # object now) so that patching / subclassing of the individual
        # ``_resolve_from_*`` methods is still honoured after construction.
        return [
            _CallableSource("local-tools.py", _local_lookup),
            _CallableSource("wrapper-registry",
                            lambda n: self._resolve_from_wrapper_registry(n)),
            _CallableSource("praisonaiagents",
                            lambda n: self._resolve_from_praisonaiagents(n)),
            _CallableSource("praisonai-tools",
                            lambda n: self._resolve_from_praisonai_tools(n)),
            _CallableSource("core-registry",
                            lambda n: self._resolve_from_registry(n)),
        ]

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
                        callable(obj)):
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
    
    def _resolve_from_praisonaiagents(self, name: str) -> _ResolveResult:
        """Resolve tool from praisonaiagents.tools.TOOL_MAPPINGS.
        
        Uses lazy loading via __getattr__ in praisonaiagents.tools.
        
        Args:
            name: Tool name to resolve
            
        Returns:
            _ResolveResult with tool and cacheable flag
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
                        # IMPORTANT: do NOT cache. The dep may be installed later.
                        return _ResolveResult(None, cacheable=False)
                    if tool is not None:
                        logger.debug(f"Resolved '{name}' from praisonaiagents.tools")
                        return _ResolveResult(tool)
            
            # Also try direct attribute access (for non-TOOL_MAPPINGS items)
            tool = getattr(agent_tools, name, None)
            if tool is not None and callable(tool):
                logger.debug(f"Resolved '{name}' from praisonaiagents.tools (direct)")
                return _ResolveResult(tool)
                
        except ImportError:
            logger.debug("praisonaiagents not available")
            # SDK can be installed later
            return _ResolveResult(None, cacheable=False)
        except AttributeError:
            pass
        except Exception as e:
            logger.debug(f"Error resolving '{name}' from praisonaiagents: {e}")
        
        # Genuinely not present
        return _ResolveResult(None)
    
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
    
    def invalidate(self, name: Optional[str] = None) -> None:
        """Invalidate cached tool lookups.
        
        Args:
            name: If specified, invalidate only this tool. Otherwise clear all.
        """
        with self._resolve_cache_lock:
            self._resolve_cache_epoch += 1
            if name is None:
                self._resolve_cache.clear()
                logger.debug("Cleared entire tool resolution cache")
            else:
                if name in self._resolve_cache:
                    del self._resolve_cache[name]
                    logger.debug(f"Invalidated cached resolution for '{name}'")
    
    def resolve(self, name: str, instantiate: bool = False) -> Optional[Callable]:
        """Resolve a tool name to a callable.
        
        Resolution order:
        1. Local tools.py (backward compat, custom tools)
        2. Wrapper ToolRegistry (register_function API)
        3. praisonaiagents.tools.TOOL_MAPPINGS (built-in)
        4. praisonai-tools package (external, optional)
        5. Core SDK tool registry (plugins)
        
        Args:
            name: Tool name to resolve
            instantiate: If True, instantiate class tools automatically
            
        Returns:
            Callable if found, None if not found
        """
        if not name or not isinstance(name, str):
            return None
        
        name = name.strip()
        if not name:
            return None

        # Fast path: hold the lock only long enough to read the cache.
        with self._resolve_cache_lock:
            cached = self._resolve_cache.get(name, _SENTINEL)
            cache_epoch = self._resolve_cache_epoch
        if cached is not _SENTINEL:
            if instantiate and self._is_class(cached):
                return cached()
            return cached

        # Slow path: do ALL source lookups OUTSIDE the cache lock so that
        # cold-start imports (praisonaiagents / praisonai_tools) and nested
        # ToolRegistry locks never serialize other resolver threads or invert
        # lock order against ToolRegistry._notify_invalidate.
        tool: Optional[Callable] = None
        cacheable = True       # whether a positive result may be cached
        allow_none_cache = True  # whether a negative (None) result may be cached

        # Walk the configured source chain. Each source may return a plain
        # callable / None, or a _ResolveResult to control cacheability. The
        # first source that yields a non-None tool wins.
        for source in self._sources:
            try:
                result = source.lookup(name)
            except Exception as e:  # a misbehaving custom source must not break resolution
                logger.debug(
                    "Source %r raised while resolving %r: %s",
                    getattr(source, "name", source), name, e,
                )
                continue

            if isinstance(result, _ResolveResult):
                if result.tool is not None:
                    tool = result.tool
                    cacheable = result.cacheable
                    logger.debug(
                        "Resolved '%s' from source %r", name,
                        getattr(source, "name", source),
                    )
                    break
                elif not result.cacheable:
                    # A transient failure (e.g. dependency may install later)
                    allow_none_cache = False
            elif result is not None:
                tool = result
                logger.debug(
                    "Resolved '%s' from source %r", name,
                    getattr(source, "name", source),
                )
                break

        # Insert: re-check under the lock, then write (positive or negative cache).
        with self._resolve_cache_lock:
            existing = self._resolve_cache.get(name, _SENTINEL)
            if existing is not _SENTINEL:
                # Another thread won the race; prefer the already-cached value.
                tool = existing
            elif cache_epoch != self._resolve_cache_epoch:
                # An invalidate()/clear_cache() ran while we resolved outside the
                # lock; the result may be stale, so return it without caching.
                logger.debug(
                    f"Tool '{name}' resolution invalidated during lookup; not caching"
                )
            elif tool is not None:
                if cacheable:
                    self._resolve_cache[name] = tool
            elif allow_none_cache:
                logger.warning(f"Tool '{name}' not found in any source")
                self._resolve_cache[name] = None
            else:
                logger.debug(f"Tool '{name}' failed transiently; not caching None")

        if tool is not None and instantiate and self._is_class(tool):
            return tool()
        return tool
    
    def _is_class(self, obj) -> bool:
        """Check if object is a class (not an instance)."""
        import inspect
        return inspect.isclass(obj)
    
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
        """Validate that all tools and toolsets referenced in YAML config can be resolved.
        
        Args:
            yaml_config: Parsed YAML configuration dict
            
        Returns:
            List of tool/toolset names that could not be resolved (empty if all valid)
        """
        missing = []
        
        roles = yaml_config.get('roles', {})
        # Also support 'agents' key for canonical format
        if not roles:
            roles = yaml_config.get('agents', {})
        
        for role_name, role_config in roles.items():
            if not isinstance(role_config, dict):
                continue
            
            # Validate tools
            tools = role_config.get('tools', [])
            if tools:
                for tool_name in tools:
                    if not tool_name or not isinstance(tool_name, str):
                        continue
                    if not self.has_tool(tool_name.strip()):
                        missing.append(tool_name)
            
            # Validate toolsets
            toolsets = role_config.get('toolsets', [])
            if toolsets:
                try:
                    from praisonaiagents.toolsets import list_toolsets
                    available_toolsets = set(list_toolsets())
                    
                    for toolset_name in toolsets:
                        if not toolset_name or not isinstance(toolset_name, str):
                            continue
                        if toolset_name.strip() not in available_toolsets:
                            missing.append(f"toolset:{toolset_name}")
                except ImportError:
                    # If toolsets module not available, mark all as missing
                    for toolset_name in toolsets:
                        if toolset_name and isinstance(toolset_name, str):
                            missing.append(f"toolset:{toolset_name}")
        
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
            self._resolve_cache_epoch += 1
    
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
    
    def resolve_toolsets(self, toolset_names: List[str]) -> List[Callable]:
        """Resolve named toolset groups to callables.
        
        Expands each toolset to tool names, then resolves to callables.
        
        Args:
            toolset_names: List of toolset names to resolve
            
        Returns:
            List of resolved callables from all toolsets
        """
        if not toolset_names:
            return []
        
        try:
            from praisonaiagents.toolsets import resolve_toolsets
            
            # Resolve toolset names to tool names
            tool_names = resolve_toolsets(toolset_names)
            logger.debug(f"Resolved toolsets {toolset_names} to tools: {tool_names}")
            
            # Resolve tool names to callables
            return self.resolve_many(tool_names)
            
        except ImportError as e:
            logger.warning(f"Toolset support unavailable: {e}")
            return []
    
    def resolve_all_from_yaml(self, yaml_config: Dict[str, Any]) -> Dict[str, Callable]:
        """Resolve every tool name referenced in a parsed YAML config.

        Walks roles[*].tools and roles[*].tasks[*].tools, resolves each via
        self.resolve(), instantiates classes, and merges in local tools.py /
        tools/ contents. Returns a {name: callable} dict ready for the adapter.
        """
        tools_dict: Dict[str, Callable] = {}
        needed: set[str] = set()
        for role_cfg in yaml_config.get('roles', {}).values():
            for t in role_cfg.get('tools') or []:
                if isinstance(t, str) and t.strip():
                    needed.add(t.strip())
            tasks = role_cfg.get('tasks') or {}
            # Handle both dict and list formats for tasks
            if isinstance(tasks, dict):
                task_list = tasks.values()
            elif isinstance(tasks, list):
                task_list = tasks
            else:
                task_list = []
            
            for task_cfg in task_list:
                if not isinstance(task_cfg, dict):
                    continue
                for t in task_cfg.get('tools') or []:
                    if isinstance(t, str) and t.strip():
                        needed.add(t.strip())

        for name in needed:
            resolved = self.resolve(name)
            if resolved is None:
                logger.warning("Tool %r not found", name)
                continue
            tools_dict[name] = resolved() if inspect.isclass(resolved) else resolved

        # Restore original mutual exclusion: tools.py OR tools/ directory, not both
        root_directory = os.getcwd()
        tools_py_path = os.path.join(root_directory, 'tools.py')
        tools_dir = Path(root_directory) / 'tools'
        
        # Load from tools.py if it exists
        local_tools = self.get_local_tool_classes()
        if local_tools:
            tools_dict.update(local_tools)
            if os.path.isfile(tools_py_path):
                logger.debug("tools.py exists in the root directory. Loading tools.py and skipping tools folder.")
        # Otherwise load from tools/ directory if it exists
        elif tools_dir.is_dir():
            tools_dict.update(self.get_local_tool_classes_from_dir(tools_dir))
            logger.debug("tools folder exists in the root directory")
        return tools_dict


    def load_functions_from_module(self, module_path: str) -> Dict[str, Callable]:
        """Public replacement for AgentsGenerator.load_tools_from_module."""
        from ._safe_loader import load_user_module
        module = load_user_module(module_path, name="tools_module")
        return {} if module is None else {
            name: obj for name, obj in inspect.getmembers(module)
            if inspect.isfunction(obj) or callable(obj)
        }


    def load_classes_from_module(self, module_path: str) -> Dict[str, Callable]:
        """Public replacement for AgentsGenerator.load_tools_from_module_class.
        Promotes _extract_tool_classes from private to public."""
        from ._safe_loader import load_user_module
        module = load_user_module(module_path, name="tools_module")
        return {} if module is None else self._extract_tool_classes(module)


    def load_functions_from_package(self, package_path: Path | str) -> Dict[str, Callable]:
        """Safe replacement that uses _safe_loader instead of importlib."""
        pkg = Path(package_path)
        out: Dict[str, Callable] = {}
        for py in pkg.glob("*.py"):
            if py.name.startswith("__"):
                continue
            out.update(self.load_functions_from_module(str(py.resolve())))
        return out
    
    def resolve_tools_and_toolsets(
        self, 
        tool_names: Optional[List[str]] = None,
        toolset_names: Optional[List[str]] = None
    ) -> List[Callable]:
        """Resolve both individual tools and toolset groups to callables.
        
        Args:
            tool_names: List of individual tool names
            toolset_names: List of toolset names to expand
            
        Returns:
            Combined list of callables from tools and toolsets
        """
        all_tools = []
        
        # Add explicit tools
        if tool_names:
            all_tools.extend(self.resolve_many(tool_names))
        
        # Add toolset tools
        if toolset_names:
            all_tools.extend(self.resolve_toolsets(toolset_names))
        
        # Deduplicate while preserving order
        deduped: List[Callable] = []
        seen: set[int] = set()
        for tool in all_tools:
            marker = id(tool)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(tool)
        return deduped


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


def resolve_toolsets(toolset_names: List[str], resolver: Optional[ToolResolver] = None) -> List[Callable]:
    """Resolve named toolset groups to callables.
    
    Args:
        toolset_names: List of toolset names to resolve
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        List of resolved callables from all toolsets
    """
    return (resolver or _get_default_resolver()).resolve_toolsets(toolset_names)


def resolve_tools_and_toolsets(
    tool_names: Optional[List[str]] = None,
    toolset_names: Optional[List[str]] = None,
    resolver: Optional[ToolResolver] = None
) -> List[Callable]:
    """Resolve both individual tools and toolset groups to callables.
    
    Args:
        tool_names: List of individual tool names
        toolset_names: List of toolset names to expand
        resolver: Optional resolver instance. If None, uses cached default resolver.
        
    Returns:
        Combined list of callables from tools and toolsets
    """
    return (resolver or _get_default_resolver()).resolve_tools_and_toolsets(tool_names, toolset_names)


