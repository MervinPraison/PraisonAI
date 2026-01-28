"""
Tool Override Loader for PraisonAI.

Allows loading custom tools from files, modules, and directories.
Supports runtime tool registration with context manager pattern.
"""

import ast
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional


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
        
        # Load the module
        spec = importlib.util.spec_from_file_location(
            f"custom_tools_{path.stem}",
            path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from: {path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        
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
    
    # 4.5. Current working directory tools.py (if exists)
    cwd_tools_py = Path.cwd() / "tools.py"
    if cwd_tools_py.exists():
        try:
            tools = loader.load_from_file(str(cwd_tools_py))
            registry.update(tools)
        except Exception:
            pass
    
    # 4. Template-local tools.py
    if template_dir:
        tools_py = Path(template_dir) / "tools.py"
        if tools_py.exists():
            try:
                tools = loader.load_from_file(str(tools_py))
                registry.update(tools)
            except Exception:
                pass
    
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


def resolve_tools(
    tool_names: List[Any],
    registry: Optional[Dict[str, Callable]] = None,
    template_dir: Optional[str] = None,
) -> List[Callable]:
    """
    Resolve tool names to callable tools from registry.
    
    Handles:
    - String tool names (looked up in registry)
    - Already-callable tools (passed through)
    - Built-in tool names (shell_tool, file_tool, etc.)
    
    Args:
        tool_names: List of tool names (strings) or callables
        registry: Tool registry to look up names in
        template_dir: Optional template directory for local tools.py autoload
        
    Returns:
        List of resolved callable tools
    """
    if not tool_names:
        return []
    
    resolved = []
    
    # Build registry if not provided
    if registry is None:
        registry = create_tool_registry_with_overrides(include_defaults=True)
    
    # Load template-local tools.py if exists
    if template_dir:
        loader = ToolOverrideLoader()
        tools_py = Path(template_dir) / "tools.py"
        if tools_py.exists():
            try:
                local_tools = loader.load_from_file(str(tools_py))
                registry.update(local_tools)
            except Exception:
                pass
    
    for tool in tool_names:
        if callable(tool):
            # Already a callable, use directly
            resolved.append(tool)
        elif isinstance(tool, str):
            # Look up by name in registry
            tool_name = tool.strip()
            
            # Try exact match first
            if tool_name in registry:
                tool_obj = registry[tool_name]
                # Handle lazy-loaded tools (tuples of module, class) - skip these
                # They should be resolved via praisonaiagents.tools.__getattr__
                if isinstance(tool_obj, tuple):
                    # Try to import from praisonaiagents.tools instead
                    try:
                        from praisonaiagents import tools as agent_tools
                        if hasattr(agent_tools, tool_name):
                            resolved.append(getattr(agent_tools, tool_name))
                            continue
                    except (ImportError, AttributeError):
                        pass
                elif callable(tool_obj):
                    resolved.append(tool_obj)
                    continue
                else:
                    # Try to instantiate if it's a class
                    try:
                        resolved.append(tool_obj())
                        continue
                    except Exception:
                        resolved.append(tool_obj)
                        continue
            
            # Not in registry or was a tuple, try variations
            variations = [
                tool_name,
                tool_name.lower(),
                tool_name.replace("-", "_"),
                tool_name.replace("_", "-"),
                f"{tool_name}_tool",
                f"{tool_name}Tool",
            ]
            found = False
            for var in variations:
                if var in registry:
                    tool_obj = registry[var]
                    if callable(tool_obj):
                        resolved.append(tool_obj)
                        found = True
                        break
            
            if not found:
                # Try to import from praisonaiagents.tools
                try:
                    from praisonaiagents import tools as agent_tools
                    if hasattr(agent_tools, tool_name):
                        resolved.append(getattr(agent_tools, tool_name))
                    elif hasattr(agent_tools, f"{tool_name}_tool"):
                        resolved.append(getattr(agent_tools, f"{tool_name}_tool"))
                except (ImportError, AttributeError):
                    pass
    
    return resolved
