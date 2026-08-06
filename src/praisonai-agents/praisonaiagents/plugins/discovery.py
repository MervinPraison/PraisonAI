"""
Plugin Discovery for Single-File Plugins.

Discovers and loads plugins from directories.
Plugins are simple Python files with WordPress-style docstring headers.

Default plugin directories (in precedence order):
1. Project: ./.praisonai/plugins/
2. User: ~/.praisonai/plugins/

Usage:
    from praisonaiagents.plugins.discovery import discover_plugins, load_plugin
    
    # Discover all plugins
    plugins = discover_plugins()
    
    # Load a specific plugin
    plugin = load_plugin("/path/to/my_plugin.py")
"""

import importlib.util
import os
import threading
from praisonaiagents._logging import get_logger
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import parse_plugin_header_from_file, PluginParseError
from ..paths import get_plugins_dir, get_project_data_dir

logger = get_logger(__name__)

# Maps a loaded plugin's generated module name to the tool names it harvested,
# so unload_plugin can unregister them instead of leaking active tools.
_loaded_plugin_tools: Dict[str, List[str]] = {}
# Guards the read-modify-write of _loaded_plugin_tools so concurrent load and
# unload calls from different threads cannot leave a tool registered with no
# tracking entry.
_loaded_plugin_tools_lock = threading.Lock()


def _project_plugins_allowed() -> bool:
    """Whether executing project-local single-file plugins is authorised.

    Single-file plugins in ``./.praisonai/plugins/*.py`` can hook every
    lifecycle event and intercept every tool call, so they are the most
    privileged extension surface. They therefore share the same opt-in trust
    gate that project-local tools use: an explicit environment flag. This
    mirrors ``PRAISONAI_ALLOW_LOCAL_TOOLS`` for tools; a cloned repo carrying a
    malicious ``.praisonai/plugins/exfil.py`` will not run until the user opts
    in.

    User-global plugins (``~/.praisonai/plugins/``) are treated as trusted
    (the user placed them there themselves), matching entry-point plugins
    installed via pip.
    """
    env = os.environ.get("PRAISONAI_ALLOW_PROJECT_PLUGINS", "").strip().lower()
    if env in ("true", "1", "yes", "on"):
        return True
    if env in ("false", "0", "no", "off"):
        return False
    try:
        from ..config.loader import get_plugins_config

        return bool(getattr(get_plugins_config(), "allow_project_plugins", False))
    except Exception:
        return False


def _is_project_local(path: Path) -> bool:
    """True when ``path`` is reached via the project-local plugins directory.

    The trust gate must fire on *how the file was reached*, not on where a
    symlink ultimately points. A repository-controlled symlink at
    ``.praisonai/plugins/evil.py -> /tmp/evil.py`` is still project-controlled
    code, so we compare the file's own (un-resolved) location against the
    project plugins directory. We resolve only the parent directories (not the
    final component) so a project ``plugins`` symlink is still recognised while
    a symlinked plugin *file* inside it cannot slip the gate by resolving
    elsewhere.
    """
    try:
        project_plugins = (get_project_data_dir() / "plugins").resolve()
    except Exception:
        return False
    try:
        # Resolve the containing directory (following any symlinked dirs) but
        # keep the file's own name un-resolved, so a symlinked plugin file is
        # judged by its location under .praisonai/plugins, not its target.
        located = path.expanduser()
        candidate = located.parent.resolve() / located.name
        candidate.relative_to(project_plugins)
        return True
    except ValueError:
        return False

def get_default_plugin_dirs() -> List[Path]:
    """Get default plugin directory locations.
    
    Uses centralized paths.py for consistent path management.
    Returns directories in precedence order (high to low):
    1. Project: ./.praisonai/plugins/
    2. User: ~/.praisonai/plugins/
    
    Returns:
        List of existing plugin directories
    """
    dirs = []
    
    # Project-level directory (use centralized path)
    project_data_dir = get_project_data_dir()
    project_plugins = project_data_dir / "plugins"
    if project_plugins.exists() and project_plugins.is_dir():
        dirs.append(project_plugins)
    
    # User-level directory (use centralized path)
    user_plugins = get_plugins_dir()
    if user_plugins.exists() and user_plugins.is_dir():
        dirs.append(user_plugins)
    
    return dirs

def discover_plugins(
    plugin_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
) -> List[Dict[str, Any]]:
    """Discover all valid plugins in the given directories.
    
    Scans directories for Python files with valid plugin headers.
    Does NOT load the plugins - just returns metadata.
    
    Args:
        plugin_dirs: List of directory paths to scan for plugins.
        include_defaults: Whether to include default plugin directories
        
    Returns:
        List of plugin metadata dictionaries
    """
    all_dirs = []
    
    # Add explicit directories
    if plugin_dirs:
        for d in plugin_dirs:
            path = Path(d).expanduser().resolve()
            if path.exists() and path.is_dir():
                all_dirs.append(path)
    
    # Add default directories
    if include_defaults:
        all_dirs.extend(get_default_plugin_dirs())
    
    # Remove duplicates while preserving order
    seen = set()
    unique_dirs = []
    for d in all_dirs:
        if d not in seen:
            seen.add(d)
            unique_dirs.append(d)
    
    plugins = []
    
    for parent_dir in unique_dirs:
        try:
            for item in parent_dir.iterdir():
                # Skip directories and non-Python files
                if item.is_dir() or item.suffix != '.py':
                    continue
                
                # Skip files starting with underscore
                if item.name.startswith('_'):
                    continue
                
                try:
                    metadata = parse_plugin_header_from_file(str(item))
                    plugins.append(metadata)
                except (PluginParseError, FileNotFoundError) as e:
                    logger.debug(f"Skipping invalid plugin {item}: {e}")
                    continue
        except PermissionError:
            logger.warning(f"Cannot read plugin directory: {parent_dir}")
            continue
    
    return plugins

def load_plugin(filepath: str) -> Optional[Dict[str, Any]]:
    """Load a single plugin file and register its tools/hooks.
    
    This function:
    1. Parses the plugin header for metadata
    2. Imports the module (which triggers @tool and @add_hook decorators)
    3. Explicitly registers any FunctionTool instances found in the module
    4. Returns the plugin metadata with discovered tools
    
    Args:
        filepath: Path to the Python plugin file
        
    Returns:
        Plugin metadata dict with 'tools' and 'hooks' lists, or None on error
    """
    # Keep the caller's location un-resolved for the trust gate so a
    # repository-controlled symlink under .praisonai/plugins cannot escape the
    # gate by pointing its target elsewhere.
    located = Path(filepath).expanduser()
    path = located.resolve()

    if not path.exists():
        logger.error(f"Plugin file not found: {filepath}")
        return None
    
    if not path.suffix == '.py':
        logger.error(f"Plugin must be a Python file: {filepath}")
        return None

    # Trust gate: project-local single-file plugins are the most privileged
    # extension surface (they can hook every lifecycle event and intercept
    # every tool call), so refuse to exec them unless explicitly authorised —
    # matching the opt-in required for project-local tools.
    if _is_project_local(located) and not _project_plugins_allowed():
        logger.warning(
            "Refusing to load project plugin %s: set "
            "PRAISONAI_ALLOW_PROJECT_PLUGINS=true (or plugins.allow_project_plugins "
            "in .praisonai/config.yaml) to enable.",
            path,
        )
        return None

    try:
        # Parse header first
        metadata = parse_plugin_header_from_file(str(path))
    except PluginParseError as e:
        logger.error(f"Invalid plugin header: {e}")
        return None
    
    # Generate unique module name to avoid conflicts
    module_name = f"praison_plugin_{path.stem}_{id(path)}"
    
    # Get registry for tool registration
    from ..tools.registry import get_registry
    from ..tools.base import BaseTool
    registry = get_registry()
    
    try:
        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            logger.error(f"Cannot create module spec for: {filepath}")
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        # Snapshot the registry before exec: the @tool decorator auto-registers
        # on module load, so any tool name present *after* exec but not before
        # is one this module contributed and therefore owns.
        try:
            pre_exec_tools = set(registry.list_tools())
        except Exception:
            pre_exec_tools = set()

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error executing plugin module {filepath}: {e}")
            del sys.modules[module_name]
            return None
        
        # Explicitly find and register any BaseTool/FunctionTool instances
        # The @tool decorator creates FunctionTool instances but may not
        # register them if the registry wasn't fully initialized
        new_tools = []
        owned_tools = []
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
            attr = getattr(module, attr_name, None)
            if isinstance(attr, BaseTool):
                tool_name = attr.name
                # Register any tool not already present (e.g. if the decorator
                # could not auto-register).
                if registry.get(tool_name) is None:
                    registry.register(attr)
                # A tool is "owned" (safe to unregister on unload) only if it
                # was absent before this module executed — tools already present
                # belong to another plugin or the core registry.
                if tool_name not in pre_exec_tools:
                    owned_tools.append(tool_name)
                new_tools.append(tool_name)
        
        # Add discovered tools to metadata
        metadata["tools"] = new_tools
        metadata["module"] = module_name
        # Remember only the tools this module actually registered so unload can
        # clean them up without removing tools still in use elsewhere.
        with _loaded_plugin_tools_lock:
            _loaded_plugin_tools[module_name] = owned_tools
        
        logger.info(f"Loaded plugin: {metadata['name']} (tools: {new_tools})")
        return metadata
        
    except Exception as e:
        logger.error(f"Failed to load plugin {filepath}: {e}")
        if module_name in sys.modules:
            del sys.modules[module_name]
        return None

def discover_and_load_plugins(
    plugin_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
) -> List[Dict[str, Any]]:
    """Discover and load all plugins from directories.
    
    Combines discover_plugins() and load_plugin() for convenience.
    
    Args:
        plugin_dirs: List of directory paths to scan
        include_defaults: Whether to include default directories
        
    Returns:
        List of loaded plugin metadata dictionaries
    """
    discovered = discover_plugins(plugin_dirs, include_defaults)
    loaded = []
    
    for plugin_meta in discovered:
        path = plugin_meta.get("path")
        if path:
            result = load_plugin(path)
            if result:
                loaded.append(result)
    
    return loaded

def unload_plugin(module_name: str) -> bool:
    """Unload a plugin module and unregister the tools it harvested.

    Removes the module from ``sys.modules`` and unregisters every tool the
    module contributed to the global tool registry, so a disable-by-unload no
    longer leaks active tools.

    Args:
        module_name: The module name (from plugin metadata)

    Returns:
        True if the module was present and unloaded, False if not found
    """
    with _loaded_plugin_tools_lock:
        tools = _loaded_plugin_tools.pop(module_name, [])
    if tools:
        try:
            from ..tools.registry import get_registry

            registry = get_registry()
            for tool_name in tools:
                try:
                    registry.unregister(tool_name)
                except Exception as e:
                    logger.debug(f"Failed to unregister tool '{tool_name}': {e}")
        except Exception as e:
            logger.debug(f"Failed to access tool registry during unload: {e}")

    if module_name in sys.modules:
        del sys.modules[module_name]
        return True
    return False

def ensure_plugin_dir() -> Path:
    """Ensure the user plugin directory exists.
    
    Creates ~/.praisonai/plugins/ if it doesn't exist.
    Uses centralized paths.py for consistent path management.
    
    Returns:
        Path to the user plugin directory
    """
    user_dir = get_plugins_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def get_plugin_template(name: str, description: str = "", author: str = "") -> str:
    """Generate a plugin template with the given metadata.
    
    Args:
        name: Plugin name
        description: Plugin description
        author: Plugin author
        
    Returns:
        Plugin template as string
    """
    return f'''"""
Plugin Name: {name}
Description: {description or "A PraisonAI plugin"}
Version: 1.0.0
Author: {author or "Your Name"}
"""

from praisonaiagents import tool

@tool
def example_tool(query: str) -> str:
    """Example tool - replace with your implementation.
    
    Args:
        query: Input query
        
    Returns:
        Result string
    """
    return f"Result: {{query}}"

# Uncomment to add hooks:
# from praisonaiagents.hooks import add_hook, HookResult
#
# @add_hook("before_tool")
# def my_hook(data):
#     """Validate tool calls."""
#     return HookResult.allow()
'''
