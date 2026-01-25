"""
Hook Registry for PraisonAI Agents.

Manages registration and lookup of hooks for different events.
"""

import logging
from typing import Dict, List, Optional, Callable, Union
from functools import wraps

from .types import (
    HookEvent, HookDefinition, CommandHook, FunctionHook,
    HookInput, HookResult
)

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Registry for managing hooks.
    
    Provides methods to register, unregister, and lookup hooks
    for different events.
    
    Example:
        registry = HookRegistry()
        
        # Register a function hook using decorator
        @registry.on(HookEvent.BEFORE_TOOL)
        def validate_tool(event_data):
            if event_data.tool_name == "dangerous":
                return HookResult.deny("Tool is dangerous")
            return HookResult.allow()
        
        # Register a command hook
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="python /path/to/validator.py",
            matcher="write_*"
        )
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the hook registry.
        
        Args:
            enabled: Whether hooks are enabled globally
        """
        self._hooks: Dict[HookEvent, List[HookDefinition]] = {
            event: [] for event in HookEvent
        }
        self._enabled = enabled
        self._global_timeout = 60.0
    
    @property
    def enabled(self) -> bool:
        """Check if hooks are enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        """Enable or disable hooks."""
        self._enabled = value
    
    def register(self, hook: HookDefinition) -> str:
        """
        Register a hook definition.
        
        Args:
            hook: The hook definition to register
            
        Returns:
            The hook ID
        """
        self._hooks[hook.event].append(hook)
        logger.debug(f"Registered hook '{hook.name}' for event '{hook.event.value}'")
        return hook.id
    
    def register_function(
        self,
        event: HookEvent,
        func: Callable[[HookInput], HookResult],
        matcher: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        sequential: bool = False,
        timeout: float = 60.0,
        is_async: bool = False
    ) -> str:
        """
        Register a Python function as a hook.
        
        Args:
            event: The event to hook
            func: The function to call
            matcher: Optional regex pattern to match targets
            name: Optional name for the hook
            description: Optional description
            sequential: Whether to run sequentially
            timeout: Timeout in seconds
            is_async: Whether the function is async
            
        Returns:
            The hook ID
        """
        hook = FunctionHook(
            event=event,
            func=func,
            matcher=matcher,
            name=name or func.__name__,
            description=description,
            sequential=sequential,
            timeout=timeout,
            is_async=is_async
        )
        return self.register(hook)
    
    def register_command(
        self,
        event: HookEvent,
        command: str,
        matcher: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        sequential: bool = False,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
        shell: bool = True
    ) -> str:
        """
        Register a shell command as a hook.
        
        Args:
            event: The event to hook
            command: The shell command to execute
            matcher: Optional regex pattern to match targets
            name: Optional name for the hook
            description: Optional description
            sequential: Whether to run sequentially
            timeout: Timeout in seconds
            env: Additional environment variables
            shell: Whether to run in shell mode
            
        Returns:
            The hook ID
        """
        hook = CommandHook(
            event=event,
            command=command,
            matcher=matcher,
            name=name,
            description=description,
            sequential=sequential,
            timeout=timeout,
            env=env or {},
            shell=shell
        )
        return self.register(hook)
    
    def on(
        self,
        event: HookEvent,
        matcher: Optional[str] = None,
        sequential: bool = False,
        timeout: float = 60.0
    ) -> Callable:
        """
        Decorator to register a function as a hook.
        
        Args:
            event: The event to hook
            matcher: Optional regex pattern to match targets
            sequential: Whether to run sequentially
            timeout: Timeout in seconds
            
        Returns:
            Decorator function
            
        Example:
            @registry.on(HookEvent.BEFORE_TOOL)
            def my_hook(event_data):
                return HookResult.allow()
        """
        def decorator(func: Callable[[HookInput], HookResult]) -> Callable:
            import asyncio
            is_async = asyncio.iscoroutinefunction(func)
            
            self.register_function(
                event=event,
                func=func,
                matcher=matcher,
                sequential=sequential,
                timeout=timeout,
                is_async=is_async
            )
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            return wrapper
        
        return decorator
    
    def unregister(self, hook_id: str) -> bool:
        """
        Unregister a hook by ID.
        
        Args:
            hook_id: The hook ID to unregister
            
        Returns:
            True if found and removed, False otherwise
        """
        for event in HookEvent:
            for i, hook in enumerate(self._hooks[event]):
                if hook.id == hook_id:
                    self._hooks[event].pop(i)
                    logger.debug(f"Unregistered hook '{hook_id}'")
                    return True
        return False
    
    def get_hooks(
        self,
        event: HookEvent,
        target: Optional[str] = None
    ) -> List[HookDefinition]:
        """
        Get all hooks for an event, optionally filtered by target.
        
        Args:
            event: The event to get hooks for
            target: Optional target to filter by (e.g., tool name)
            
        Returns:
            List of matching hook definitions
        """
        if not self._enabled:
            return []
        
        hooks = self._hooks.get(event, [])
        
        if target is None:
            return [h for h in hooks if h.enabled]
        
        return [h for h in hooks if h.enabled and h.matches(target)]
    
    def has_hooks(self, event: HookEvent) -> bool:
        """Check if there are any hooks registered for an event."""
        return bool(self.get_hooks(event))
    
    def clear(self, event: Optional[HookEvent] = None):
        """
        Clear all hooks or hooks for a specific event.
        
        Args:
            event: Optional event to clear hooks for
        """
        if event is None:
            for e in HookEvent:
                self._hooks[e] = []
        else:
            self._hooks[event] = []
    
    def list_hooks(self) -> Dict[str, List[Dict]]:
        """
        List all registered hooks.
        
        Returns:
            Dictionary mapping event names to hook info
        """
        result = {}
        for event in HookEvent:
            hooks = self._hooks[event]
            if hooks:
                result[event.value] = [
                    {
                        "id": h.id,
                        "name": h.name,
                        "type": "command" if isinstance(h, CommandHook) else "function",
                        "matcher": h.matcher,
                        "enabled": h.enabled,
                        "sequential": h.sequential
                    }
                    for h in hooks
                ]
        return result
    
    def enable_hook(self, hook_id: str) -> bool:
        """Enable a specific hook."""
        for event in HookEvent:
            for hook in self._hooks[event]:
                if hook.id == hook_id:
                    hook.enabled = True
                    return True
        return False
    
    def disable_hook(self, hook_id: str) -> bool:
        """Disable a specific hook."""
        for event in HookEvent:
            for hook in self._hooks[event]:
                if hook.id == hook_id:
                    hook.enabled = False
                    return True
        return False
    
    def set_global_timeout(self, timeout: float):
        """Set the global timeout for all hooks."""
        self._global_timeout = timeout
    
    def __len__(self) -> int:
        """Get total number of registered hooks."""
        return sum(len(hooks) for hooks in self._hooks.values())
    
    def __repr__(self) -> str:
        return f"HookRegistry(enabled={self._enabled}, hooks={len(self)})"


# Global default registry
_default_registry: Optional[HookRegistry] = None


def get_default_registry() -> HookRegistry:
    """Get the default global hook registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = HookRegistry()
    return _default_registry


def set_default_registry(registry: HookRegistry):
    """Set the default global hook registry."""
    global _default_registry
    _default_registry = registry


# =============================================================================
# Simplified API (beginner-friendly aliases)
# =============================================================================
# These functions provide a simpler, beginner-friendly API for hook management.
# They accept both string event names ('before_tool') and HookEvent enums.
# =============================================================================

def add_hook(
    event: Union[str, HookEvent],
    callback: Optional[Callable[[HookInput], HookResult]] = None,
    priority: int = 10,
    matcher: Optional[str] = None
) -> Union[str, Callable]:
    """Register a hook callback. Simplified API.
    
    Accepts both string event names and HookEvent enums:
        add_hook('before_tool', my_callback)  # String
        add_hook(HookEvent.BEFORE_TOOL, my_callback)  # Enum
    
    Can also be used as a decorator:
        @add_hook('before_tool')
        def my_hook(data):
            return HookResult.allow()
    
    Args:
        event: Hook event name ('before_tool', 'after_llm', etc.) or HookEvent enum
        callback: Function to call when hook fires (optional when using as decorator)
        priority: Execution order (lower = earlier). Default 10. (Reserved for future use)
        matcher: Optional regex pattern to match specific targets (e.g., tool names)
        
    Returns:
        Hook ID for later removal, or a decorator function if callback is None
        
    Raises:
        ValueError: If event string is not a valid HookEvent
    """
    # Normalize string to HookEvent
    if isinstance(event, str):
        try:
            event = HookEvent(event)
        except ValueError:
            valid_events = [e.value for e in HookEvent]
            raise ValueError(
                f"Unknown hook event: '{event}'. "
                f"Valid events: {', '.join(valid_events)}"
            )
    
    # If callback is None, return a decorator
    if callback is None:
        def decorator(func: Callable[[HookInput], HookResult]) -> Callable:
            get_default_registry().register_function(
                event=event,
                func=func,
                matcher=matcher
            )
            return func
        return decorator
    
    return get_default_registry().register_function(
        event=event,
        func=callback,
        matcher=matcher
    )


def remove_hook(hook_id: str) -> bool:
    """Remove a hook by ID. Simplified API.
    
    Args:
        hook_id: The hook ID returned by add_hook()
        
    Returns:
        True if hook was found and removed, False otherwise
    """
    return get_default_registry().unregister(hook_id)


def has_hook(event: Union[str, HookEvent]) -> bool:
    """Check if any hooks are registered for an event. Simplified API.
    
    Accepts both string event names and HookEvent enums:
        has_hook('before_tool')  # String
        has_hook(HookEvent.BEFORE_TOOL)  # Enum
    
    Args:
        event: Hook event name or HookEvent enum
        
    Returns:
        True if hooks are registered for this event
        
    Raises:
        ValueError: If event string is not a valid HookEvent
    """
    # Normalize string to HookEvent
    if isinstance(event, str):
        try:
            event = HookEvent(event)
        except ValueError:
            valid_events = [e.value for e in HookEvent]
            raise ValueError(
                f"Unknown hook event: '{event}'. "
                f"Valid events: {', '.join(valid_events)}"
            )
    
    return get_default_registry().has_hooks(event)
