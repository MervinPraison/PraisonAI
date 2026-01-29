"""
Built-in Plugins for PraisonAI Agents.

Provides ready-to-use plugins for common functionality.

Usage:
    from praisonaiagents.plugins.builtin import LoggingPlugin, MetricsPlugin
    
    # Use with PluginManager
    manager = PluginManager()
    manager.register(LoggingPlugin())
    manager.register(MetricsPlugin())
"""

__all__ = [
    "LoggingPlugin",
    "MetricsPlugin",
]


def __getattr__(name: str):
    """Lazy load built-in plugins."""
    if name == "LoggingPlugin":
        from .logging_plugin import LoggingPlugin
        return LoggingPlugin
    
    if name == "MetricsPlugin":
        from .metrics_plugin import MetricsPlugin
        return MetricsPlugin
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
