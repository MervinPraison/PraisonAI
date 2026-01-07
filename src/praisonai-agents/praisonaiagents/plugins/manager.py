"""
Plugin Manager for PraisonAI Agents.

Provides dynamic plugin discovery, loading, and lifecycle management.
"""

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from .plugin import Plugin, PluginHook, PluginInfo, FunctionPlugin

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages plugin discovery, loading, and execution.
    
    Example:
        manager = PluginManager()
        
        # Load plugins from directory
        manager.load_from_directory("./plugins")
        
        # Register a plugin directly
        manager.register(MyPlugin())
        
        # Execute hooks
        args = manager.execute_hook(PluginHook.BEFORE_TOOL, "bash", {"cmd": "ls"})
    """
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._enabled: Dict[str, bool] = {}
    
    def register(self, plugin: Plugin) -> bool:
        """
        Register a plugin.
        
        Args:
            plugin: The plugin to register
            
        Returns:
            True if registered successfully
        """
        try:
            info = plugin.info
            if info.name in self._plugins:
                logger.warning(f"Plugin '{info.name}' already registered")
                return False
            
            self._plugins[info.name] = plugin
            self._enabled[info.name] = True
            
            # Initialize plugin
            plugin.on_init({})
            
            logger.info(f"Registered plugin: {info.name} v{info.version}")
            return True
        except Exception as e:
            logger.error(f"Failed to register plugin: {e}")
            return False
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a plugin.
        
        Args:
            name: The plugin name
            
        Returns:
            True if unregistered successfully
        """
        if name not in self._plugins:
            return False
        
        try:
            plugin = self._plugins[name]
            plugin.on_shutdown()
        except Exception as e:
            logger.warning(f"Error during plugin shutdown: {e}")
        
        del self._plugins[name]
        del self._enabled[name]
        
        logger.info(f"Unregistered plugin: {name}")
        return True
    
    def enable(self, name: str) -> bool:
        """Enable a plugin."""
        if name in self._enabled:
            self._enabled[name] = True
            return True
        return False
    
    def disable(self, name: str) -> bool:
        """Disable a plugin."""
        if name in self._enabled:
            self._enabled[name] = False
            return True
        return False
    
    def is_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled."""
        return self._enabled.get(name, False)
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[PluginInfo]:
        """List all registered plugins."""
        return [p.info for p in self._plugins.values()]
    
    def load_from_directory(self, directory: str) -> int:
        """
        Load plugins from a directory.
        
        Looks for Python files with a `create_plugin` function
        or classes that inherit from Plugin.
        
        Args:
            directory: Path to the plugins directory
            
        Returns:
            Number of plugins loaded
        """
        directory = Path(directory)
        if not directory.exists():
            logger.warning(f"Plugin directory does not exist: {directory}")
            return 0
        
        loaded = 0
        
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            try:
                plugin = self._load_plugin_file(file_path)
                if plugin and self.register(plugin):
                    loaded += 1
            except Exception as e:
                logger.error(f"Failed to load plugin from {file_path}: {e}")
        
        return loaded
    
    def _load_plugin_file(self, file_path: Path) -> Optional[Plugin]:
        """Load a plugin from a Python file."""
        module_name = f"praison_plugin_{file_path.stem}"
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error loading module {file_path}: {e}")
            del sys.modules[module_name]
            return None
        
        # Look for create_plugin function
        if hasattr(module, "create_plugin"):
            return module.create_plugin()
        
        # Look for Plugin subclass
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
                and obj is not FunctionPlugin
            ):
                return obj()
        
        return None
    
    def load_from_module(self, module_path: str) -> bool:
        """
        Load a plugin from a module path.
        
        Args:
            module_path: Dotted module path (e.g., "mypackage.plugins.myplugin")
            
        Returns:
            True if loaded successfully
        """
        try:
            module = importlib.import_module(module_path)
            
            if hasattr(module, "create_plugin"):
                plugin = module.create_plugin()
                return self.register(plugin)
            
            # Look for Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                    and obj is not FunctionPlugin
                ):
                    return self.register(obj())
            
            return False
        except Exception as e:
            logger.error(f"Failed to load plugin from module {module_path}: {e}")
            return False
    
    def execute_hook(
        self,
        hook: PluginHook,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a hook across all enabled plugins.
        
        Args:
            hook: The hook to execute
            *args: Arguments to pass to hook
            **kwargs: Keyword arguments to pass to hook
            
        Returns:
            The result (may be modified by plugins)
        """
        result = args[0] if args else None
        
        for name, plugin in self._plugins.items():
            if not self._enabled.get(name, False):
                continue
            
            if hook not in plugin.info.hooks:
                continue
            
            try:
                method = getattr(plugin, hook.value, None)
                if method:
                    if hook == PluginHook.BEFORE_TOOL:
                        result = method(args[0], args[1] if len(args) > 1 else {})
                    elif hook == PluginHook.AFTER_TOOL:
                        result = method(args[0], args[1] if len(args) > 1 else None)
                    elif hook == PluginHook.BEFORE_AGENT:
                        result = method(args[0], kwargs.get("context", {}))
                    elif hook == PluginHook.AFTER_AGENT:
                        result = method(args[0], kwargs.get("context", {}))
                    elif hook == PluginHook.BEFORE_LLM:
                        result = method(args[0], args[1] if len(args) > 1 else {})
                    elif hook == PluginHook.AFTER_LLM:
                        result = method(args[0], kwargs.get("usage", {}))
                    else:
                        result = method(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error executing hook {hook.value} in plugin {name}: {e}")
        
        return result
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tools from all enabled plugins."""
        tools = []
        
        for name, plugin in self._plugins.items():
            if not self._enabled.get(name, False):
                continue
            
            try:
                plugin_tools = plugin.get_tools()
                tools.extend(plugin_tools)
            except Exception as e:
                logger.error(f"Error getting tools from plugin {name}: {e}")
        
        return tools
    
    def shutdown(self):
        """Shutdown all plugins."""
        for name in list(self._plugins.keys()):
            self.unregister(name)


# Global plugin manager instance
_default_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = PluginManager()
    return _default_manager
