"""
Plugin Module for PraisonAI Agents.

Provides dynamic plugin loading and hook-based extension system.

Features:
- Dynamic plugin discovery and loading
- Hook-based extension points
- Protocol-driven plugin interfaces
- Built-in plugins (logging, metrics)
- Plugin SDK for easy plugin development

Folder Structure:
- plugins/sdk/       - Plugin SDK (base classes, decorators)
- plugins/builtin/   - Built-in plugins (logging, metrics)
- plugins/protocols.py - Plugin protocols for type safety

Usage:
    from praisonaiagents.plugins import PluginManager, Plugin, PluginHook
    
    # Create plugin manager
    manager = PluginManager()
    
    # Load plugins from directory
    manager.load_from_directory("./plugins")
    
    # Use built-in plugins
    from praisonaiagents.plugins.builtin import LoggingPlugin, MetricsPlugin
    manager.register(LoggingPlugin())
    
    # Use plugin SDK
    from praisonaiagents.plugins.sdk import plugin
    
    @plugin(name="my_plugin", hooks=[PluginHook.BEFORE_TOOL])
    def my_plugin_func(hook_type, *args, **kwargs):
        return args[0] if args else None
"""

__all__ = [
    # Easy enable API
    "enable",
    "disable",
    "list_plugins",
    "is_enabled",
    # Core
    "PluginManager",
    "Plugin",
    "PluginHook",
    "PluginType",
    "PluginInfo",
    "FunctionPlugin",
    "get_plugin_manager",
    # Protocols
    "PluginProtocol",
    "ToolPluginProtocol",
    "HookPluginProtocol",
    "AgentPluginProtocol",
    "LLMPluginProtocol",
    # Single-file plugin support
    "PluginMetadata",
    "PluginParseError",
    "parse_plugin_header",
    "parse_plugin_header_from_file",
    "discover_plugins",
    "load_plugin",
    "discover_and_load_plugins",
    "get_default_plugin_dirs",
    "get_plugin_template",
    "ensure_plugin_dir",
]


# ============================================================================
# EASY ENABLE API
# ============================================================================
# These functions provide a simple way to enable/disable plugins globally.
# Zero performance impact when not called - plugins only load on enable().
# ============================================================================

# Global state for plugin system (lazy initialized)
_plugins_enabled: bool = False
_enabled_plugin_names: list = None  # None = all, list = specific


def enable(plugins: list = None) -> None:
    """Enable the plugin system.
    
    Discovers and enables plugins from default directories.
    This is the main entry point for using plugins.
    
    Args:
        plugins: Optional list of plugin names to enable.
                 If None, enables all discovered plugins.
    
    Examples:
        # Enable all discovered plugins
        from praisonaiagents import plugins
        plugins.enable()
        
        # Enable specific plugins only
        plugins.enable(["logging", "metrics"])
    
    Note:
        - Tools and guardrails work WITHOUT calling enable()
        - Only background plugins (hooks, metrics, logging) need enable()
        - Can also be enabled via PRAISONAI_PLUGINS env var
        - Can also be enabled via .praisonai/config.toml
    """
    global _plugins_enabled, _enabled_plugin_names
    
    _plugins_enabled = True
    _enabled_plugin_names = plugins  # None = all, list = specific
    
    # Get plugin manager and auto-discover
    from .manager import get_plugin_manager
    manager = get_plugin_manager()
    
    # Auto-discover plugins from default directories
    manager.auto_discover_plugins()
    
    # Enable specific plugins or all
    if plugins is not None:
        # Enable only specified plugins
        for name in plugins:
            manager.enable(name)
    else:
        # Enable all discovered plugins
        for plugin_info in manager.list_plugins():
            manager.enable(plugin_info.get("name", ""))
    
    import logging
    logging.debug(f"Plugins enabled: {plugins if plugins else 'all'}")


def disable(plugins: list = None) -> None:
    """Disable plugins.
    
    Args:
        plugins: Optional list of plugin names to disable.
                 If None, disables all plugins.
    
    Examples:
        # Disable all plugins
        plugins.disable()
        
        # Disable specific plugins
        plugins.disable(["logging"])
    """
    global _plugins_enabled, _enabled_plugin_names
    
    from .manager import get_plugin_manager
    manager = get_plugin_manager()
    
    if plugins is not None:
        # Disable specific plugins
        for name in plugins:
            manager.disable(name)
    else:
        # Disable all plugins
        _plugins_enabled = False
        _enabled_plugin_names = None
        for plugin_info in manager.list_plugins():
            manager.disable(plugin_info.get("name", ""))


def list_plugins() -> list:
    """List all discovered plugins.
    
    Returns:
        List of plugin info dicts with name, version, enabled status.
    
    Example:
        from praisonaiagents import plugins
        all_plugins = plugins.list_plugins()
        for p in all_plugins:
            print(f"{p['name']} v{p['version']} - {'enabled' if p['enabled'] else 'disabled'}")
    """
    from .manager import get_plugin_manager
    manager = get_plugin_manager()
    
    # Auto-discover if not already done
    if not manager._plugins and not manager._single_file_plugins:
        manager.auto_discover_plugins()
    
    # Combine registered plugins and single-file plugins
    result = []
    
    # Add registered plugins (Plugin class instances)
    for info in manager.list_plugins():
        if hasattr(info, 'name'):
            # PluginInfo object
            result.append({
                "name": info.name,
                "version": getattr(info, 'version', '1.0.0'),
                "description": getattr(info, 'description', ''),
                "enabled": manager.is_enabled(info.name),
                "type": "registered",
            })
        elif isinstance(info, dict):
            # Already a dict
            info["enabled"] = manager.is_enabled(info.get("name", ""))
            info["type"] = "registered"
            result.append(info)
    
    # Add single-file plugins
    for name, meta in manager._single_file_plugins.items():
        result.append({
            "name": name,
            "version": meta.get("version", "1.0.0"),
            "description": meta.get("description", ""),
            "enabled": manager.is_enabled(name),
            "type": "single_file",
        })
    
    return result


def is_enabled(name: str = None) -> bool:
    """Check if plugins are enabled.
    
    Args:
        name: Optional plugin name to check. If None, checks if system is enabled.
    
    Returns:
        True if enabled, False otherwise.
    """
    global _plugins_enabled
    
    if name is None:
        return _plugins_enabled
    
    from .manager import get_plugin_manager
    manager = get_plugin_manager()
    return manager.is_enabled(name)


def __getattr__(name: str):
    """Lazy load module components."""
    # Core classes
    if name == "PluginManager":
        from .manager import PluginManager
        return PluginManager
    
    if name == "get_plugin_manager":
        from .manager import get_plugin_manager
        return get_plugin_manager
    
    if name == "Plugin":
        from .plugin import Plugin
        return Plugin
    
    if name == "PluginHook":
        from .plugin import PluginHook
        return PluginHook
    
    if name == "PluginInfo":
        from .plugin import PluginInfo
        return PluginInfo
    
    if name == "FunctionPlugin":
        from .plugin import FunctionPlugin
        return FunctionPlugin
    
    if name == "PluginType":
        from .plugin import PluginType
        return PluginType
    
    # Protocols
    if name == "PluginProtocol":
        from .protocols import PluginProtocol
        return PluginProtocol
    
    if name == "ToolPluginProtocol":
        from .protocols import ToolPluginProtocol
        return ToolPluginProtocol
    
    if name == "HookPluginProtocol":
        from .protocols import HookPluginProtocol
        return HookPluginProtocol
    
    if name == "AgentPluginProtocol":
        from .protocols import AgentPluginProtocol
        return AgentPluginProtocol
    
    if name == "LLMPluginProtocol":
        from .protocols import LLMPluginProtocol
        return LLMPluginProtocol
    
    # Single-file plugin support - parser
    if name == "PluginMetadata":
        from .parser import PluginMetadata
        return PluginMetadata
    
    if name == "PluginParseError":
        from .parser import PluginParseError
        return PluginParseError
    
    if name == "parse_plugin_header":
        from .parser import parse_plugin_header
        return parse_plugin_header
    
    if name == "parse_plugin_header_from_file":
        from .parser import parse_plugin_header_from_file
        return parse_plugin_header_from_file
    
    # Single-file plugin support - discovery
    if name == "discover_plugins":
        from .discovery import discover_plugins
        return discover_plugins
    
    if name == "load_plugin":
        from .discovery import load_plugin
        return load_plugin
    
    if name == "discover_and_load_plugins":
        from .discovery import discover_and_load_plugins
        return discover_and_load_plugins
    
    if name == "get_default_plugin_dirs":
        from .discovery import get_default_plugin_dirs
        return get_default_plugin_dirs
    
    if name == "get_plugin_template":
        from .discovery import get_plugin_template
        return get_plugin_template
    
    if name == "ensure_plugin_dir":
        from .discovery import ensure_plugin_dir
        return ensure_plugin_dir
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
