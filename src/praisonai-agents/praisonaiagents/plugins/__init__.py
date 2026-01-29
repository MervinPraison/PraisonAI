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
    # Core
    "PluginManager",
    "Plugin",
    "PluginHook",
    "PluginInfo",
    "FunctionPlugin",
    "get_plugin_manager",
    # Protocols
    "PluginProtocol",
    "ToolPluginProtocol",
    "HookPluginProtocol",
    "AgentPluginProtocol",
    "LLMPluginProtocol",
]


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
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
