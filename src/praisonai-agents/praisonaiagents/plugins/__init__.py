"""
Plugin Module for PraisonAI Agents.

Provides dynamic plugin loading and hook-based extension system.

Features:
- Dynamic plugin discovery and loading
- Hook-based extension points
- Tool plugins
- Auth plugins
- Configuration plugins

Usage:
    from praisonaiagents.plugins import PluginManager
    
    # Create plugin manager
    manager = PluginManager()
    
    # Load plugins from directory
    manager.load_from_directory("./plugins")
    
    # Get loaded plugins
    plugins = manager.list_plugins()
"""

__all__ = [
    "PluginManager",
    "Plugin",
    "PluginHook",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "PluginManager":
        from .manager import PluginManager
        return PluginManager
    
    if name == "Plugin":
        from .plugin import Plugin
        return Plugin
    
    if name == "PluginHook":
        from .plugin import PluginHook
        return PluginHook
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
