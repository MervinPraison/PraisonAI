"""
Plugin Manager for PraisonAI Agents.

Provides dynamic plugin discovery, loading, and lifecycle management.
Thread-safe and async-safe for multi-agent environments.
"""

import asyncio
import importlib.util
import logging
from praisonaiagents._logging import get_logger
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TYPE_CHECKING

from .plugin import Plugin, PluginHook, PluginInfo, FunctionPlugin

if TYPE_CHECKING:
    from ..hooks.registry import HookRegistry
    from ..hooks.types import HookEvent

logger = get_logger(__name__)

class PluginManager:
    """
    Manages plugin discovery, loading, and execution.
    
    Thread-safe for concurrent access in multi-agent environments.
    Supports both sync and async hook execution.
    
    Example:
        manager = PluginManager()
        
        # Load plugins from directory
        manager.load_from_directory("./plugins")
        
        # Register a plugin directly
        manager.register(MyPlugin())
        
        # Execute hooks (sync)
        args = manager.execute_hook(PluginHook.BEFORE_TOOL, "bash", {"cmd": "ls"})
        
        # Execute hooks (async)
        args = await manager.async_execute_hook(PluginHook.BEFORE_TOOL, "bash", {"cmd": "ls"})
    """
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._enabled: Dict[str, bool] = {}
        self._single_file_plugins: Dict[str, Dict[str, Any]] = {}  # WordPress-style plugins
        self._lock = threading.RLock()  # Thread safety for multi-agent environments
    
    def register(self, plugin: Plugin) -> bool:
        """
        Register a plugin.
        
        Args:
            plugin: The plugin to register
            
        Returns:
            True if registered successfully
        """
        with self._lock:
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
        """Disable a plugin.

        Also removes any hooks the plugin previously wired into the runtime
        hook registry, so disabling actually stops its lifecycle methods from
        firing during subsequent agent execution.
        """
        if name in self._enabled:
            self._enabled[name] = False
            try:
                self.unwire_from_hook_registry(name)
            except Exception as e:
                logger.debug(f"Failed to unwire plugin '{name}': {e}")
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
    
    async def async_execute_hook(
        self,
        hook: PluginHook,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a hook across all enabled plugins asynchronously.
        
        Async-safe for use in async agent contexts.
        
        Args:
            hook: The hook to execute
            *args: Arguments to pass to hook
            **kwargs: Keyword arguments to pass to hook
            
        Returns:
            The result (may be modified by plugins)
        """
        # Use the sync version in an executor to avoid blocking
        # This is safe because execute_hook is thread-safe with _lock
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute_hook(hook, *args, **kwargs)
        )
    
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
    
    # =========================================================================
    # Single-File Plugin Support (WordPress-style)
    # =========================================================================
    
    def load_single_file_plugin(self, filepath: str) -> bool:
        """
        Load a single-file plugin with WordPress-style docstring header.
        
        This is the SIMPLEST plugin format - just a Python file with:
        - A docstring header at the top with metadata
        - @tool decorated functions for tools
        - @add_hook decorated functions for hooks
        
        Example plugin file:
            '''
            Plugin Name: Weather Tools
            Description: Get weather for any city
            Version: 1.0.0
            '''
            
            from praisonaiagents import tool
            
            @tool
            def get_weather(city: str) -> str:
                return f"Weather in {city}"
        
        Args:
            filepath: Path to the Python plugin file
            
        Returns:
            True if loaded successfully
        """
        from .discovery import load_plugin
        
        result = load_plugin(filepath)
        if result is None:
            return False
        
        # Track the loaded plugin metadata
        name = result.get("name", "Unknown")
        self._single_file_plugins[name] = result
        
        logger.info(f"Loaded single-file plugin: {name}")
        return True
    
    def load_single_file_plugins_from_directory(
        self,
        directory: str,
        include_defaults: bool = False
    ) -> int:
        """
        Load all single-file plugins from a directory.
        
        Args:
            directory: Path to scan for plugin files
            include_defaults: Also scan default plugin directories
            
        Returns:
            Number of plugins loaded
        """
        from .discovery import discover_and_load_plugins
        
        dirs = [directory] if directory else []
        loaded = discover_and_load_plugins(dirs, include_defaults)
        
        # Track loaded plugins
        for plugin_meta in loaded:
            name = plugin_meta.get("name", "Unknown")
            self._single_file_plugins[name] = plugin_meta
        
        return len(loaded)
    
    def auto_discover_plugins(self) -> int:
        """
        Auto-discover and load plugins from default directories.
        
        Scans:
        - ./.praisonai/plugins/ (project-level)
        - ~/.praisonai/plugins/ (user-level)
        
        Returns:
            Number of plugins loaded
        """
        import os

        if os.environ.get("PRAISONAI_ALLOW_PLUGIN_DISCOVERY", "").strip().lower() not in (
            "true", "1", "yes",
        ):
            logger.debug(
                "Plugin auto-discovery disabled; set PRAISONAI_ALLOW_PLUGIN_DISCOVERY=true"
            )
            return 0

        from .discovery import discover_and_load_plugins
        
        loaded = discover_and_load_plugins(plugin_dirs=None, include_defaults=True)
        
        for plugin_meta in loaded:
            name = plugin_meta.get("name", "Unknown")
            self._single_file_plugins[name] = plugin_meta
        
        return len(loaded)
    
    def list_single_file_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded single-file plugins."""
        return list(self._single_file_plugins.values())
    
    def get_single_file_plugin(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a single-file plugin by name."""
        return self._single_file_plugins.get(name)
    
    def discover_entry_points(self) -> int:
        """
        Auto-discover and load protocol-driven plugins installed via pip
        that register in the ``praisonai.plugins`` entry-point group.

        This is the group declared by the ``praisonai-plugins`` package.
        Compatible with Python 3.8+ using importlib.metadata.

        Returns:
            Number of plugins loaded successfully.
        """
        try:
            import importlib.metadata as _md
        except ImportError:
            logger.debug("importlib.metadata not available. Cannot discover plugins.")
            return 0

        try:
            # Python 3.10+ style - selectable entry points
            entry_points = _md.entry_points(group="praisonai.plugins")
        except TypeError:
            # Python 3.8/3.9 fallback - dict-like interface
            try:
                entry_points = _md.entry_points().get("praisonai.plugins", [])
            except Exception as e:
                logger.error(f"Failed to get entry points: {e}")
                return 0

        loaded = 0
        # Use lock to ensure thread-safe discovery of multiple entry points.
        # register() also acquires the lock but that's fine (RLock allows re-entry).
        with self._lock:
            for ep in entry_points:
                try:
                    plugin_cls = ep.load()
                    if callable(plugin_cls):
                        plugin = plugin_cls()
                        if self.register(plugin):
                            loaded += 1
                            logger.info(f"Loaded entry_point plugin: {ep.name}")
                    else:
                        logger.warning(f"Entry point {ep.name} is not callable")
                except Exception as e:
                    logger.error(f"Failed to load plugin from entry point {ep.name}: {e}")

        return loaded

    # =========================================================================
    # Hook Registry Bridge (connect discovered plugins to the runtime engine)
    # =========================================================================

    def wire_into_hook_registry(self, registry: Optional["HookRegistry"] = None) -> int:
        """
        Bridge enabled plugins into the runtime hook engine.

        Each enabled ``Plugin``'s lifecycle methods are adapted into
        ``HookDefinition``s and registered on the hook registry that the
        Agent's ``HookRunner`` actually consults. Without this bridge, plugins
        discovered via entry points are registered but never fired during real
        agent/bot execution.

        Args:
            registry: Target hook registry. Defaults to the global default
                registry (the one the Agent runtime uses).

        Returns:
            Number of hook definitions registered.
        """
        from ..hooks.registry import get_default_registry

        registry = registry if registry is not None else get_default_registry()

        count = 0
        with self._lock:
            for name, plugin in self._plugins.items():
                if not self._enabled.get(name, False):
                    continue
                if getattr(plugin, "_wired_into_registry", None) is registry:
                    # Avoid double-registration on repeated enable() calls
                    continue
                hook_ids: List[str] = []
                for event, func in _adapt_plugin_hooks(plugin):
                    hook_id = registry.register_function(
                        event=event,
                        func=func,
                        name=f"{name}:{event.value}",
                    )
                    hook_ids.append(hook_id)
                    count += 1
                try:
                    plugin._wired_into_registry = registry
                    plugin._wired_hook_ids = hook_ids
                except Exception:
                    pass
        return count

    def unwire_from_hook_registry(self, name: str) -> int:
        """
        Remove a plugin's previously wired hooks from its hook registry.

        Complements :meth:`wire_into_hook_registry` so that ``disable()`` on a
        plugin that was already bridged actually stops its lifecycle methods
        from firing during subsequent agent execution.

        Args:
            name: The plugin name to unwire.

        Returns:
            Number of hook definitions removed.
        """
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                return 0
            registry = getattr(plugin, "_wired_into_registry", None)
            if registry is None:
                return 0
            removed = 0
            for hook_id in getattr(plugin, "_wired_hook_ids", []) or []:
                if registry.unregister(hook_id):
                    removed += 1
            try:
                plugin._wired_into_registry = None
                plugin._wired_hook_ids = []
            except Exception:
                pass
            return removed

def _write_back(data, attr: str, new_value: dict) -> None:
    """Write a plugin's returned dict back onto the hook payload.

    Mutates the existing dict in place when present (preserving object
    identity for callers that hold a reference), otherwise assigns the value
    directly so first-time injection (e.g. ``credentials`` starting as
    ``None``) is not silently dropped.
    """
    current = getattr(data, attr, None)
    if isinstance(current, dict):
        current.clear()
        current.update(new_value)
        return
    try:
        setattr(data, attr, new_value)
    except Exception:
        pass


def _adapt_plugin_hooks(plugin: Plugin) -> Iterator[Tuple["HookEvent", Callable]]:
    """
    Adapt a plugin's overridden lifecycle methods into hook functions.

    Yields ``(HookEvent, func)`` pairs where ``func`` takes a ``HookInput`` and
    returns a ``HookResult``. Only methods the plugin actually overrides (or
    declares in ``PluginInfo.hooks``) are adapted, so plugins that implement a
    single guardrail don't get spuriously invoked for every event.

    Mutations are applied in place on the ``HookInput`` payload where the core
    runtime reads them back (e.g. ``before_llm_input.messages`` in chat_mixin),
    matching the existing BEFORE_LLM contract.
    """
    from ..hooks.types import HookEvent, HookResult

    base = Plugin

    def _overrides(method_name: str) -> bool:
        # Declared in PluginInfo.hooks OR overridden on the concrete class
        try:
            declared = getattr(plugin.info, "hooks", None) or []
            declared_values = {h.value if hasattr(h, "value") else h for h in declared}
            if method_name in declared_values:
                return True
        except Exception:
            pass
        own = getattr(type(plugin), method_name, None)
        parent = getattr(base, method_name, None)
        return own is not None and own is not parent

    def _permission_result(value: Optional[bool], reason: str) -> HookResult:
        if value is True:
            return HookResult.allow(reason)
        if value is False:
            return HookResult.deny(reason)
        return HookResult.allow()

    if _overrides("before_agent"):
        def before_agent_hook(data, _p=plugin):
            new_prompt = _p.before_agent(getattr(data, "prompt", ""),
                                         {"agent_name": getattr(data, "agent_name", None)})
            if isinstance(new_prompt, str) and hasattr(data, "prompt"):
                data.prompt = new_prompt
            return HookResult.allow()
        yield HookEvent.BEFORE_AGENT, before_agent_hook

    if _overrides("after_agent"):
        def after_agent_hook(data, _p=plugin):
            new_resp = _p.after_agent(getattr(data, "response", ""),
                                      {"agent_name": getattr(data, "agent_name", None)})
            if isinstance(new_resp, str) and hasattr(data, "response"):
                data.response = new_resp
            return HookResult.allow()
        yield HookEvent.AFTER_AGENT, after_agent_hook

    if _overrides("before_llm"):
        def before_llm_hook(data, _p=plugin):
            messages = getattr(data, "messages", [])
            result = _p.before_llm(messages, {"model": getattr(data, "model", "")})
            if isinstance(result, tuple) and result and isinstance(result[0], list):
                if hasattr(data, "messages"):
                    data.messages[:] = result[0]
            return HookResult.allow()
        yield HookEvent.BEFORE_LLM, before_llm_hook

    if _overrides("after_llm"):
        def after_llm_hook(data, _p=plugin):
            new_resp = _p.after_llm(getattr(data, "response", ""),
                                    {"tokens_used": getattr(data, "tokens_used", 0)})
            if isinstance(new_resp, str) and hasattr(data, "response"):
                data.response = new_resp
            return HookResult.allow()
        yield HookEvent.AFTER_LLM, after_llm_hook

    if _overrides("before_tool"):
        def before_tool_hook(data, _p=plugin):
            args = getattr(data, "tool_input", {}) or {}
            new_args = _p.before_tool(getattr(data, "tool_name", ""), args)
            if isinstance(new_args, dict) and isinstance(getattr(data, "tool_input", None), dict):
                data.tool_input.clear()
                data.tool_input.update(new_args)
            return HookResult.allow()
        yield HookEvent.BEFORE_TOOL, before_tool_hook

    if _overrides("after_tool"):
        def after_tool_hook(data, _p=plugin):
            _p.after_tool(getattr(data, "tool_name", ""), getattr(data, "tool_output", None))
            return HookResult.allow()
        yield HookEvent.AFTER_TOOL, after_tool_hook

    if _overrides("before_tool_definitions"):
        def before_tool_definitions_hook(data, _p=plugin):
            defs = getattr(data, "tool_definitions", []) or []
            new_defs = _p.before_tool_definitions(defs)
            if isinstance(new_defs, list) and isinstance(getattr(data, "tool_definitions", None), list):
                data.tool_definitions[:] = new_defs
            return HookResult.allow()
        yield HookEvent.BEFORE_TOOL_DEFINITIONS, before_tool_definitions_hook

    if _overrides("before_message"):
        def before_message_hook(data, _p=plugin):
            content = getattr(data, "content", "")
            new = _p.before_message({"content": content})
            if isinstance(new, dict) and "content" in new and hasattr(data, "content"):
                data.content = new["content"]
            return HookResult.allow()
        yield HookEvent.MESSAGE_RECEIVED, before_message_hook

    if _overrides("after_message"):
        def after_message_hook(data, _p=plugin):
            content = getattr(data, "content", "")
            new = _p.after_message({"content": content})
            if isinstance(new, dict) and "content" in new and hasattr(data, "content"):
                data.content = new["content"]
            return HookResult.allow()
        yield HookEvent.MESSAGE_SENDING, after_message_hook

    if _overrides("on_permission_ask"):
        def on_permission_ask_hook(data, _p=plugin):
            target = getattr(data, "tool_name", "") or getattr(data, "target", "")
            reason = getattr(data, "reason", "") or "Permission requested"
            return _permission_result(_p.on_permission_ask(target, reason), reason)
        yield HookEvent.ON_PERMISSION_ASK, on_permission_ask_hook

    if _overrides("on_config"):
        def on_config_hook(data, _p=plugin):
            config = getattr(data, "config", None)
            if not isinstance(config, dict):
                config = getattr(data, "extra", {}) or {}
            new_config = _p.on_config(config)
            if isinstance(new_config, dict):
                _write_back(data, "config", new_config)
            return HookResult.allow()
        yield HookEvent.ON_CONFIG, on_config_hook

    if _overrides("on_auth"):
        def on_auth_hook(data, _p=plugin):
            auth_type = getattr(data, "auth_type", "") or ""
            credentials = getattr(data, "credentials", None) or {}
            new_creds = _p.on_auth(auth_type, credentials)
            if isinstance(new_creds, dict):
                _write_back(data, "credentials", new_creds)
            return HookResult.allow()
        yield HookEvent.ON_AUTH, on_auth_hook

    if _overrides("session_start"):
        def session_start_hook(data, _p=plugin):
            _p.session_start({
                "source": getattr(data, "source", None),
                "session_name": getattr(data, "session_name", None),
                "session_id": getattr(data, "session_id", None),
            })
            return HookResult.allow()
        yield HookEvent.SESSION_START, session_start_hook

    if _overrides("session_end"):
        def session_end_hook(data, _p=plugin):
            _p.session_end({
                "reason": getattr(data, "reason", None),
                "total_turns": getattr(data, "total_turns", None),
                "total_tokens": getattr(data, "total_tokens", None),
                "session_id": getattr(data, "session_id", None),
            })
            return HookResult.allow()
        yield HookEvent.SESSION_END, session_end_hook

    if _overrides("on_error"):
        def on_error_hook(data, _p=plugin):
            _p.on_error(
                getattr(data, "error_type", "") or "",
                getattr(data, "error_message", "") or "",
                {
                    "stack_trace": getattr(data, "stack_trace", None),
                    "context": getattr(data, "context", {}) or {},
                    "session_id": getattr(data, "session_id", None),
                },
            )
            return HookResult.allow()
        yield HookEvent.ON_ERROR, on_error_hook


# Global plugin manager instance
_default_manager: Optional[PluginManager] = None

def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = PluginManager()
    return _default_manager
