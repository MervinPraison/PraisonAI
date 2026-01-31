"""
Plugin Discovery for Single-File Plugins.

Discovers and loads plugins from directories.
Plugins are simple Python files with WordPress-style docstring headers.

Default plugin directories (in precedence order):
1. Project: ./.praison/plugins/
2. User: ~/.praison/plugins/

Usage:
    from praisonaiagents.plugins.discovery import discover_plugins, load_plugin
    
    # Discover all plugins
    plugins = discover_plugins()
    
    # Load a specific plugin
    plugin = load_plugin("/path/to/my_plugin.py")
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import parse_plugin_header_from_file, PluginParseError

logger = logging.getLogger(__name__)


def get_default_plugin_dirs() -> List[Path]:
    """Get default plugin directory locations.
    
    Returns directories in precedence order (high to low):
    1. Project: ./.praison/plugins/
    2. User: ~/.praison/plugins/
    
    Returns:
        List of existing plugin directories
    """
    dirs = []
    cwd = Path.cwd()
    
    # Project-level directory
    project_dir = cwd / ".praison" / "plugins"
    if project_dir.exists() and project_dir.is_dir():
        dirs.append(project_dir)
    
    # User-level directory
    user_dir = Path.home() / ".praison" / "plugins"
    if user_dir.exists() and user_dir.is_dir():
        dirs.append(user_dir)
    
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
    path = Path(filepath).resolve()
    
    if not path.exists():
        logger.error(f"Plugin file not found: {filepath}")
        return None
    
    if not path.suffix == '.py':
        logger.error(f"Plugin must be a Python file: {filepath}")
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
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
            attr = getattr(module, attr_name, None)
            if isinstance(attr, BaseTool):
                tool_name = attr.name
                # Register if not already registered
                if registry.get(tool_name) is None:
                    registry.register(attr)
                new_tools.append(tool_name)
        
        # Add discovered tools to metadata
        metadata["tools"] = new_tools
        metadata["module"] = module_name
        
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
    """Unload a plugin module.
    
    Note: This removes the module from sys.modules but does NOT
    unregister tools or hooks that were already registered.
    
    Args:
        module_name: The module name (from plugin metadata)
        
    Returns:
        True if unloaded, False if not found
    """
    if module_name in sys.modules:
        del sys.modules[module_name]
        return True
    return False


def ensure_plugin_dir() -> Path:
    """Ensure the user plugin directory exists.
    
    Creates ~/.praison/plugins/ if it doesn't exist.
    
    Returns:
        Path to the user plugin directory
    """
    user_dir = Path.home() / ".praison" / "plugins"
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
