"""
Plugin decorators for PraisonAI Agents.

Provides decorator-based plugin creation for simpler use cases.
"""

from functools import wraps
from typing import Callable, List, Optional

from ..plugin import FunctionPlugin, PluginHook


def plugin(
    name: str,
    hooks: Optional[List[PluginHook]] = None,
    version: str = "1.0.0",
    description: str = "",
) -> Callable:
    """
    Decorator to create a simple plugin from a function.
    
    The decorated function will be called for all specified hooks.
    
    Args:
        name: Plugin name
        hooks: List of hooks to register for (default: [BEFORE_TOOL])
        version: Plugin version
        description: Plugin description
        
    Returns:
        Decorator function
        
    Example:
        @plugin(name="my_plugin", hooks=[PluginHook.BEFORE_TOOL])
        def my_plugin_func(hook_type, *args, **kwargs):
            if hook_type == PluginHook.BEFORE_TOOL:
                tool_name, tool_args = args
                return tool_args  # Return modified args
            return args[0] if args else None
    """
    if hooks is None:
        hooks = [PluginHook.BEFORE_TOOL]
    
    def decorator(func: Callable) -> FunctionPlugin:
        hook_map = {}
        
        for hook in hooks:
            @wraps(func)
            def hook_handler(*args, _hook=hook, **kwargs):
                return func(_hook, *args, **kwargs)
            
            hook_map[hook] = hook_handler
        
        return FunctionPlugin(
            name=name,
            hooks=hook_map,
            version=version,
            description=description,
        )
    
    return decorator
