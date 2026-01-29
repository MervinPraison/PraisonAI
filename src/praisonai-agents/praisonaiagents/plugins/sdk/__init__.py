"""
Plugin SDK for PraisonAI Agents.

Provides the base classes, decorators, and utilities for building plugins.

Usage:
    from praisonaiagents.plugins.sdk import Plugin, PluginHook, plugin
    
    # Class-based plugin
    class MyPlugin(Plugin):
        @property
        def info(self) -> PluginInfo:
            return PluginInfo(name="my_plugin", version="1.0.0")
        
        def before_tool(self, tool_name: str, args: dict) -> dict:
            return args
    
    # Decorator-based plugin
    @plugin(name="simple_plugin", hooks=[PluginHook.BEFORE_TOOL])
    def my_plugin_func(event_data):
        return event_data
"""

__all__ = [
    "Plugin",
    "PluginInfo",
    "PluginHook",
    "FunctionPlugin",
    "plugin",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name in ("Plugin", "PluginInfo", "PluginHook", "FunctionPlugin"):
        from ..plugin import Plugin, PluginInfo, PluginHook, FunctionPlugin
        return locals()[name]
    
    if name == "plugin":
        from .decorators import plugin
        return plugin
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
