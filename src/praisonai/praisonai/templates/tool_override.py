"""
Tool Override Loader for PraisonAI.

Allows loading custom tools from files, modules, and directories.
Supports runtime tool registration with context manager pattern.
"""

import ast
import importlib
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Memoisation cache for ToolResolver instances built by resolve_tools().
# Keyed on (id(registry), template_dir, autoload_enabled) so that repeated
# calls within a single workflow build (once per agent/step, over the same
# registry object) reuse one resolver and its per-instance caches instead of
# rebuilding the registry+resolver and re-executing local tools.py per agent.
# The registry object is also stored to guard against id() reuse after GC.
_resolver_cache: Dict[Any, Any] = {}


def _load_user_module_safe(path: Path, *, name: str):
    """Load a user ``.py`` file through the canonical safe loader.

    This routes the actual ``exec_module`` through
    :func:`praisonai_code._safe_loader.load_user_module`, so the wrapper no
    longer maintains a second, divergent loader with a raw
    ``spec.loader.exec_module`` call. There is now a single owner for
    user-module execution and a single security gate.

    Callers of ``load_from_file`` / ``load_from_directory`` pass explicit,
    user-provided paths (the wrapper's historical contract only rejects
    remote URLs). To preserve that behaviour on top of the canonical gate --
    which requires ``PRAISONAI_ALLOW_LOCAL_TOOLS=true`` -- we authorize this
    single explicit load in-process via ``skip_env_check=True`` and use
    ``allow_outside_cwd=True`` (the same treatment the canonical resolver
    gives explicit ``--tools`` paths in
    :meth:`ToolResolver.load_functions_from_module`).

    ``skip_env_check`` is a thread-safe, per-call opt-in: unlike temporarily
    mutating the process-wide ``PRAISONAI_ALLOW_LOCAL_TOOLS`` env var, it does
    not leak authorization to concurrent threads that read the gate. The
    implicit ``tools.py`` autoload path keeps its own
    ``PRAISONAI_ALLOW_TEMPLATE_TOOLS`` opt-in layered above this helper.
    """
    from praisonai._bootstrap import ensure_praisonai_code

    ensure_praisonai_code()
    from praisonai_code._safe_loader import load_user_module

    return load_user_module(
        str(path), name=name, allow_outside_cwd=True, skip_env_check=True
    )


def _autoload_tools_enabled() -> bool:
    """Return True when implicit ``tools.py`` autoload is opted in.

    Loading and executing arbitrary ``tools.py`` files from a recipe
    template directory or the current working directory is unsafe whenever
    the recipe source is not fully trusted (e.g. when it was fetched from
    a remote registry such as GitHub). We therefore disable the implicit
    autoload by default and require explicit opt-in.

    The env var ``PRAISONAI_ALLOW_TEMPLATE_TOOLS`` is honored to keep
    legacy local workflows working without a code change.
    """
    val = os.environ.get("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "").strip().lower()
    return val in ("1", "true", "yes", "on")


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


class ToolOverrideLoader:
    """
    Loads custom tools from various sources.
    
    Supports:
    - Python file paths
    - Module import paths
    - Directories containing tool files
    
    Security:
    - Only local paths allowed by default
    - Remote URLs rejected
    - No auto-execution of arbitrary code
    """
    
    # Default custom tool directories
    DEFAULT_TOOL_DIRS = [
        "~/.praison/tools",
        "~/.config/praison/tools",
    ]
    
    def __init__(self):
        """Initialize tool override loader."""
        self._loaded_tools: Dict[str, Callable] = {}
    
    def get_default_tool_dirs(self) -> List[Path]:
        """
        Get default custom tool directories.
        
        Returns:
            List of Path objects for default tool directories
        """
        return [Path(d).expanduser() for d in self.DEFAULT_TOOL_DIRS]
    
    def load_from_file(self, file_path: str) -> Dict[str, Callable]:
        """
        Load tools from a Python file.
        
        Args:
            file_path: Path to Python file containing tool functions
            
        Returns:
            Dict mapping tool names to callable functions
            
        Raises:
            SecurityError: If path is a remote URL
            FileNotFoundError: If file doesn't exist
        """
        # Security check - reject remote URLs
        if file_path.startswith(("http://", "https://", "ftp://")):
            raise SecurityError(
                f"Remote URLs not allowed for security: {file_path}. "
                "Only local file paths are permitted."
            )
        
        path = Path(file_path).expanduser().resolve()
        
        if not path.exists():
            raise FileNotFoundError(f"Tool file not found: {path}")
        
        if not path.suffix == ".py":
            raise ValueError(f"Tool file must be a Python file (.py): {path}")
        
        # Load the module through the canonical safe loader (single owner of
        # user-module execution + single security gate). See
        # ``_load_user_module_safe`` for how the wrapper's explicit-load
        # contract is preserved on top of the canonical opt-in.
        module = _load_user_module_safe(path, name=f"custom_tools_{path.stem}")
        if module is None:
            raise ImportError(f"Could not load module from: {path}")
        
        # Extract callable functions (tools)
        tools = {}
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj) and not isinstance(obj, type):
                tools[name] = obj
        
        self._loaded_tools.update(tools)
        return tools
    
    def load_from_module(self, module_path: str) -> Dict[str, Callable]:
        """
        Load tools from a module import path.
        
        Args:
            module_path: Python module path (e.g., 'mypackage.tools')
            
        Returns:
            Dict mapping tool names to callable functions
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"Could not import module: {module_path}") from e
        
        # Extract callable functions (tools)
        tools = {}
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj) and not isinstance(obj, type):
                tools[name] = obj
        
        self._loaded_tools.update(tools)
        return tools
    
    def load_from_directory(self, dir_path: str) -> Dict[str, Callable]:
        """
        Load tools from all Python files in a directory.
        
        Args:
            dir_path: Path to directory containing tool files
            
        Returns:
            Dict mapping tool names to callable functions
            
        Raises:
            SecurityError: If path is a remote URL
        """
        # Security check
        if dir_path.startswith(("http://", "https://", "ftp://")):
            raise SecurityError(
                f"Remote URLs not allowed for security: {dir_path}. "
                "Only local directory paths are permitted."
            )
        
        path = Path(dir_path).expanduser().resolve()
        
        if not path.exists():
            raise FileNotFoundError(f"Tool directory not found: {path}")
        
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
        
        tools = {}
        for py_file in path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                file_tools = self.load_from_file(str(py_file))
                tools.update(file_tools)
            except Exception:
                # Skip files that fail to load
                pass
        
        return tools
    
    def discover_tools_in_directory(self, dir_path: str) -> List[str]:
        """
        Discover tool names in a directory without executing code.
        
        Uses AST parsing to find function definitions.
        
        Args:
            dir_path: Path to directory to scan
            
        Returns:
            List of discovered tool function names
        """
        path = Path(dir_path).expanduser().resolve()
        
        if not path.exists() or not path.is_dir():
            return []
        
        tool_names = []
        for py_file in path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        if not node.name.startswith("_"):
                            tool_names.append(node.name)
            except Exception:
                # Skip files that fail to parse
                pass
        
        return tool_names
    
    @contextmanager
    def override_context(
        self,
        files: Optional[List[str]] = None,
        modules: Optional[List[str]] = None,
        directories: Optional[List[str]] = None
    ) -> Generator[Dict[str, Callable], None, None]:
        """
        Context manager for temporary tool overrides.
        
        Tools loaded within this context are available only during
        the context and are cleaned up afterward.
        
        Args:
            files: List of Python file paths to load
            modules: List of module paths to import
            directories: List of directories to scan
            
        Yields:
            Dict of loaded tools
        """
        # Store original state
        original_tools = self._loaded_tools.copy()
        
        try:
            # Load tools from all sources
            loaded = {}
            
            if files:
                for f in files:
                    loaded.update(self.load_from_file(f))
            
            if modules:
                for m in modules:
                    loaded.update(self.load_from_module(m))
            
            if directories:
                for d in directories:
                    loaded.update(self.load_from_directory(d))
            
            yield loaded
            
        finally:
            # Restore original state
            self._loaded_tools = original_tools
    
    def get_loaded_tools(self) -> Dict[str, Callable]:
        """
        Get all currently loaded tools.
        
        Returns:
            Dict mapping tool names to callable functions
        """
        return self._loaded_tools.copy()
    
    def clear_loaded_tools(self) -> None:
        """Clear all loaded tools."""
        self._loaded_tools.clear()


def create_tool_registry_with_overrides(
    override_files: Optional[List[str]] = None,
    override_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
    tools_sources: Optional[List[str]] = None,
    template_dir: Optional[str] = None,
) -> Dict[str, Callable]:
    """
    Create a tool registry with custom overrides.
    
    Resolution order (highest priority first):
    1. Override files (explicit CLI --tools)
    2. Override directories (explicit CLI --tools-dir)
    3. Template tools_sources (from TEMPLATE.yaml)
    4. Template-local tools.py
    4.5. Current working directory tools.py (./tools.py)
    5. Default custom dirs (~/.praison/tools, etc.)
    6. Package discovery (praisonai-tools if installed)
    7. Built-in tools
    
    Args:
        override_files: Explicit tool files to load
        override_dirs: Directories to scan for tools
        include_defaults: Whether to include default tool directories
        tools_sources: Template-declared tool sources (modules or paths)
        template_dir: Template directory for local tools.py
        
    Returns:
        Dict mapping tool names to callable functions
    """
    registry = {}
    loader = ToolOverrideLoader()
    
    # 7. Start with built-in tools (lowest priority)
    # Note: We don't copy TOOL_MAPPINGS directly because it contains tuples
    # (module_path, class_name) that need to be resolved via __getattr__.
    # The tools will be resolved on-demand in resolve_tools() via getattr().
    pass
    
    # 6. Package discovery - try praisonai-tools if installed
    try:
        import praisonai_tools.tools as external_tools
        # Get all exported tools from praisonai_tools
        for name in dir(external_tools):
            if not name.startswith('_'):
                obj = getattr(external_tools, name, None)
                if callable(obj) or (hasattr(obj, 'run') and callable(getattr(obj, 'run', None))):
                    registry[name] = obj
    except ImportError:
        pass
    
    # 5. Add default custom dirs
    if include_defaults:
        for dir_path in loader.get_default_tool_dirs():
            if dir_path.exists():
                try:
                    tools = loader.load_from_directory(str(dir_path))
                    registry.update(tools)
                except Exception:
                    pass
    
    # 4.5/4. Implicit ``tools.py`` autoload is only honored when the operator
    # explicitly opts in via the ``PRAISONAI_ALLOW_TEMPLATE_TOOLS`` environment
    # variable. This prevents arbitrary code execution when recipes are
    # fetched from remote registries (e.g. GitHub) where ``tools.py`` cannot
    # be considered trusted. Explicit ``override_files`` / ``override_dirs``
    # / ``tools_sources`` continue to work and are the supported way to load
    # custom tool modules.
    if _autoload_tools_enabled():
        # 4.5. Current working directory tools.py (if exists)
        cwd_tools_py = Path.cwd() / "tools.py"
        if cwd_tools_py.exists():
            try:
                tools = loader.load_from_file(str(cwd_tools_py))
                registry.update(tools)
            except Exception:
                # Skip-on-error is the documented contract here, but log
                # at debug level so opt-in users can troubleshoot a
                # broken cwd ``tools.py`` without us going silent.
                logger.debug(
                    "failed to autoload cwd tools.py at %s", cwd_tools_py,
                    exc_info=True,
                )

        # 4. Template-local tools.py
        if template_dir:
            tools_py = Path(template_dir) / "tools.py"
            if tools_py.exists():
                try:
                    tools = loader.load_from_file(str(tools_py))
                    registry.update(tools)
                except Exception:
                    logger.debug(
                        "failed to autoload template tools.py at %s", tools_py,
                        exc_info=True,
                    )
    
    # 3. Template tools_sources (from TEMPLATE.yaml)
    if tools_sources:
        for source in tools_sources:
            try:
                # Security: only allow local paths and python modules
                if source.startswith(("http://", "https://", "ftp://")):
                    continue  # Skip remote URLs
                
                source_path = Path(source).expanduser()
                
                if source_path.exists():
                    # It's a local path
                    if source_path.is_file() and source_path.suffix == ".py":
                        tools = loader.load_from_file(str(source_path))
                        registry.update(tools)
                    elif source_path.is_dir():
                        tools = loader.load_from_directory(str(source_path))
                        registry.update(tools)
                else:
                    # Try as a Python module path
                    tools = loader.load_from_module(source)
                    registry.update(tools)
            except Exception:
                pass
    
    # 2. Add override directories (CLI --tools-dir)
    if override_dirs:
        for dir_path in override_dirs:
            try:
                tools = loader.load_from_directory(dir_path)
                registry.update(tools)
            except Exception:
                pass
    
    # 1. Add override files (highest priority, CLI --tools)
    if override_files:
        for file_path in override_files:
            try:
                tools = loader.load_from_file(file_path)
                registry.update(tools)
            except Exception:
                pass
    
    return registry


def _get_resolver(
    registry: Optional[Dict[str, Callable]],
    template_dir: Optional[str],
):
    """Build or reuse a ToolResolver for the given registry/template_dir.

    Memoised on ``(id(registry), template_dir, autoload_enabled)`` so that the
    repeated per-agent/per-step calls a workflow build makes over the *same*
    registry object share one resolver (and its per-instance caches), instead
    of rebuilding the registry+resolver and re-executing local ``tools.py``
    once per agent. Resolution order and results are unchanged.
    """
    from ..tool_resolver import ToolResolver
    from ..tool_registry import ToolRegistry

    # Build registry if not provided (for backward compat with existing callers)
    if registry is None:
        registry = create_tool_registry_with_overrides(include_defaults=True)

    autoload = _autoload_tools_enabled()
    cache_key = (id(registry), template_dir, autoload)

    cached = _resolver_cache.get(cache_key)
    # Guard against id() reuse after GC: verify the stored registry is the same
    # object we were passed before returning the cached resolver.
    if cached is not None and cached[0] is registry:
        return cached[1]

    # Create a ToolRegistry instance for high-priority overrides
    tool_registry = ToolRegistry()

    # Don't manually load template tools here; let ToolResolver handle it to
    # avoid double-execution. Populate tool_registry ONLY with registry
    # overrides, which have HIGHER priority than template tools in ToolResolver.
    if registry:
        # Filter out lazy-loaded tuples from registry and register callables
        for name, tool in registry.items():
            if not isinstance(tool, tuple):
                if callable(tool):
                    tool_registry.register_function(name, tool)
                elif hasattr(tool, "run") and callable(getattr(tool, "run", None)):
                    # Support non-callable tools with a run method
                    def make_callable(t):
                        return lambda *args, **kwargs: t.run(*args, **kwargs)
                    tool_registry.register_function(name, make_callable(tool))

    # Only pass template tools path if autoload is enabled (security gate)
    template_tools_path = None
    if template_dir and autoload:
        template_tools_path = str(Path(template_dir) / "tools.py")

    # Create ToolResolver with the registry having highest priority.
    # Template tools will only be loaded if autoload is enabled.
    resolver = ToolResolver(
        tools_py_path=template_tools_path,
        registry=tool_registry
    )

    _resolver_cache[cache_key] = (registry, resolver)
    return resolver


def resolve_tools(
    tool_names: List[Any],
    registry: Optional[Dict[str, Callable]] = None,
    template_dir: Optional[str] = None,
) -> List[Callable]:
    """
    Resolve tool names to callable tools from registry.
    
    Delegates to ToolResolver for consistent resolution across all surfaces,
    while preserving template-dir autoload and registry overrides.
    
    Handles:
    - String tool names (looked up via ToolResolver)
    - Already-callable tools (passed through)
    - Name variations (lower, _/-, _tool suffix)
    - Template-local tools.py autoload (security-gated)
    
    Args:
        tool_names: List of tool names (strings) or callables
        registry: Tool registry to look up names in (for backward compat)
        template_dir: Optional template directory for local tools.py autoload
        
    Returns:
        List of resolved callable tools
    """
    if not tool_names:
        return []
    
    resolved = []
    
    # Build (or reuse) the ToolResolver once per (registry, template_dir).
    # Callers loop over agents/steps passing the same registry object, so a
    # memoised resolver preserves its per-instance caches and avoids
    # re-executing local tools.py once per agent.
    resolver = _get_resolver(registry, template_dir)
    
    for tool in tool_names:
        if callable(tool):
            # Already a callable, use directly
            resolved.append(tool)
        elif isinstance(tool, str):
            tool_name = tool.strip()
            
            # FIX from Gemini: Use instantiate=False and handle instantiation manually
            # This prevents crashes if a class requires constructor arguments
            fn = resolver.resolve(tool_name, instantiate=False)
            
            # If not found, try name variations (backward compat)
            if fn is None:
                variations = [
                    tool_name.lower(),
                    tool_name.replace("-", "_"),
                    tool_name.replace("_", "-"),
                    f"{tool_name}_tool",
                    f"{tool_name}Tool",
                ]
                for var in variations:
                    if var != tool_name:  # Skip if same as original
                        fn = resolver.resolve(var, instantiate=False)
                        if fn is not None:
                            logger.debug(f"Resolved '{tool_name}' as variation '{var}'")
                            break
            
            if fn is not None:
                # Try to instantiate if it's a class
                if isinstance(fn, type):
                    try:
                        fn = fn()
                    except Exception:
                        # If instantiation fails, use the class itself
                        # (backward compat with tools that require args)
                        pass
                resolved.append(fn)
    
    return resolved
