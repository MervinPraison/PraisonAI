"""
Advanced Tools Framework for PraisonAI Agents

Provides enhanced tool decorators with hooks, caching, external execution,
and structured input validation. Follows AGENTS.md protocol-first design.
"""

import functools
import inspect
import time
import threading
from typing import Any, Callable, List, Optional, Union, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Thread-safe global state
_lock = threading.RLock()
_cache_storage: Dict[str, Tuple[Any, float, Optional[float]]] = {}  # value, timestamp, ttl
_cache_metadata: Dict[str, Dict[str, Any]] = {}
_global_hooks: Dict[str, List[Callable]] = {"before": [], "after": []}
_external_handlers: Dict[str, Callable] = {}


class Priority(Enum):
    """Hook execution priority levels."""
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


@dataclass
class ToolContext:
    """Context passed to hooks and external handlers."""
    tool_name: str
    args: tuple
    kwargs: dict
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class Hook:
    """Hook configuration with priority and handler."""
    handler: Callable
    priority: Priority = Priority.NORMAL
    
    def __post_init__(self):
        if not callable(self.handler):
            raise ValueError("Hook handler must be callable")


@dataclass
class CacheConfig:
    """Cache configuration for tools."""
    enabled: bool = True
    ttl: Optional[float] = None  # seconds
    key_generator: Optional[Callable] = None
    when: Optional[Callable] = None  # conditional caching


@dataclass
class ExternalConfig:
    """External execution configuration."""
    executor: str
    when: Optional[Callable] = None  # conditional execution


# Input validation classes
@dataclass
class Field:
    """Field metadata for structured inputs."""
    name: str
    description: str = ""
    required: bool = True
    default: Any = None
    validator: Optional[Callable] = None


@dataclass
class InputGroup:
    """Group of related input fields."""
    name: str
    fields: List[Field]
    description: str = ""


@dataclass
class Choice:
    """Choice constraint for input fields."""
    options: List[str]
    
    def __post_init__(self):
        if not self.options:
            raise ValueError("Choice options cannot be empty")


@dataclass
class Range:
    """Range constraint for numeric inputs."""
    min_val: float
    max_val: float
    
    def __post_init__(self):
        if self.min_val >= self.max_val:
            raise ValueError("min_val must be less than max_val")


@dataclass  
class Pattern:
    """Pattern constraint for string inputs."""
    regex: str


def _generate_cache_key(tool_name: str, args: tuple, kwargs: dict) -> str:
    """Generate cache key from tool name and arguments."""
    import hashlib
    content = f"{tool_name}:{args}:{sorted(kwargs.items())}"
    hash_key = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{tool_name}:{hash_key}"


def _is_cache_valid(key: str) -> bool:
    """Check if cached value is still valid."""
    with _lock:
        if key not in _cache_storage:
            return False
        
        _, timestamp, ttl = _cache_storage[key]
        if ttl is None:
            return True
        
        return (time.time() - timestamp) < ttl


def _run_hooks(hook_type: str, context: ToolContext) -> None:
    """Run hooks of specified type with error handling."""
    with _lock:
        hooks = _global_hooks.get(hook_type, [])
    
    # Sort by priority (highest first)  
    hooks = sorted(hooks, key=lambda h: h.priority.value, reverse=True)
    
    for hook in hooks:
        try:
            if inspect.iscoroutinefunction(hook.handler):
                import asyncio
                if asyncio.iscoroutinefunction(hook.handler):
                    # Skip async hooks in sync context for now
                    continue
            hook.handler(context)
        except Exception as e:
            # Hook errors shouldn't break tool execution
            print(f"Hook error in {hook_type}: {e}")


def _handle_external_execution(func: Callable, context: ToolContext, external_config: ExternalConfig) -> Any:
    """Handle external execution with proper async support."""
    # Check condition if provided
    if external_config.when:
        try:
            if not external_config.when(*context.args, **context.kwargs):
                return func(*context.args, **context.kwargs)
        except Exception:
            # If condition check fails, fall back to normal execution
            return func(*context.args, **context.kwargs)
    
    # Look for registered external handler
    with _lock:
        handler = _external_handlers.get(external_config.executor)
    
    if handler:
        try:
            if inspect.iscoroutinefunction(handler):
                import asyncio
                return asyncio.run(handler(func, context, external_config))
            else:
                return handler(func, context, external_config)
        except Exception as e:
            print(f"External handler error: {e}")
            # Fall back to normal execution
            return func(*context.args, **context.kwargs)
    
    # No handler found, execute normally
    return func(*context.args, **context.kwargs)


def advanced_tool(name_or_func: Union[str, Callable, None] = None, **decorator_kwargs) -> Union[Callable, Any]:
    """
    Enhanced tool decorator with hooks, caching, and external execution support.
    
    Supports both @advanced_tool and @advanced_tool() usage patterns.
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
        
        # Extract configurations from kwargs
        cache_config = decorator_kwargs.get('cache')
        external_config = decorator_kwargs.get('external')  
        user_input_config = decorator_kwargs.get('user_input')
        hooks_config = decorator_kwargs.get('hooks', {})
        
        # Store metadata
        with _lock:
            _cache_metadata[tool_name] = {
                'cache': cache_config,
                'external': external_config,
                'user_input': user_input_config,
                'hooks': hooks_config,
                'original_func': func
            }
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = ToolContext(
                tool_name=tool_name,
                args=args, 
                kwargs=kwargs,
                metadata=_cache_metadata.get(tool_name, {})
            )
            
            # Run before hooks
            _run_hooks("before", context)
            
            result = None
            cache_key = None
            
            try:
                # Check cache first
                if cache_config and cache_config.enabled:
                    key_gen = cache_config.key_generator or _generate_cache_key
                    cache_key = key_gen(tool_name, args, kwargs)
                    
                    if _is_cache_valid(cache_key):
                        with _lock:
                            result, _, _ = _cache_storage[cache_key]
                        context.metadata['cache_hit'] = True
                    else:
                        context.metadata['cache_hit'] = False
                
                # Execute if not cached
                if result is None:
                    if external_config:
                        result = _handle_external_execution(func, context, external_config)
                    else:
                        result = func(*args, **kwargs)
                    
                    # Cache the result
                    if cache_config and cache_config.enabled and cache_key:
                        # Check caching condition
                        should_cache = True
                        if cache_config.when:
                            try:
                                should_cache = cache_config.when(result, *args, **kwargs)
                            except Exception:
                                should_cache = False
                        
                        if should_cache:
                            with _lock:
                                _cache_storage[cache_key] = (result, time.time(), cache_config.ttl)
                
                context.metadata['result'] = result
                
                # Run after hooks  
                _run_hooks("after", context)
                
                return result
                
            except Exception as e:
                context.metadata['error'] = e
                _run_hooks("after", context)
                raise
        
        # Store additional metadata on the wrapper
        wrapper._tool_name = tool_name
        wrapper._cache_config = cache_config
        wrapper._external_config = external_config
        wrapper._user_input_config = user_input_config
        
        return wrapper
    
    # Handle both @tool and @tool() usage patterns
    if callable(name_or_func) and not isinstance(name_or_func, str):
        # @tool (bare usage)
        return decorator(name_or_func)
    else:
        # @tool() or @tool("name")  
        return decorator


# Convenience decorators
def cache(ttl: Optional[float] = None, key_generator: Optional[Callable] = None, 
          when: Optional[Callable] = None):
    """Convenience decorator for adding caching to tools."""
    config = CacheConfig(enabled=True, ttl=ttl, key_generator=key_generator, when=when)
    return lambda func: advanced_tool(func, cache=config)


def external(executor_or_func: Union[str, Callable, None] = None, when: Optional[Callable] = None):
    """Convenience decorator for external execution."""
    if callable(executor_or_func) and not isinstance(executor_or_func, str):
        # @external (bare usage) - use function name as executor
        func = executor_or_func
        config = ExternalConfig(executor=func.__name__, when=when)
        return advanced_tool(func, external=config)
    else:
        # @external() or @external("executor_name")
        executor_name = executor_or_func or "default"
        config = ExternalConfig(executor=executor_name, when=when)
        return lambda func: advanced_tool(func, external=config)


def user_input(*fields, **groups):
    """Convenience decorator for structured user inputs."""
    return lambda func: advanced_tool(func, user_input={'fields': fields, 'groups': groups})


# Management functions
def set_global_hooks(before: List[Hook] = None, after: List[Hook] = None) -> None:
    """Set global hooks for all tools."""
    with _lock:
        if before is not None:
            _global_hooks["before"] = before
        if after is not None:
            _global_hooks["after"] = after


def clear_global_hooks() -> None:
    """Clear all global hooks."""
    with _lock:
        _global_hooks.clear()
        _global_hooks.update({"before": [], "after": []})


def register_external_handler(executor: str, handler: Callable) -> None:
    """Register an external execution handler."""
    with _lock:
        _external_handlers[executor] = handler


def invalidate_cache(tool_name: str = None) -> None:
    """Invalidate cache for specific tool or all tools."""
    with _lock:
        if tool_name is None:
            _cache_storage.clear()
        else:
            keys_to_remove = [k for k in _cache_storage if k.startswith(f"{tool_name}:")]
            for key in keys_to_remove:
                del _cache_storage[key]


def clear_all_caches() -> None:
    """Clear all cached data."""
    with _lock:
        _cache_storage.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    with _lock:
        total_entries = len(_cache_storage)
        expired_entries = sum(1 for k in _cache_storage.keys() if not _is_cache_valid(k))
        
        return {
            'total_entries': total_entries,
            'active_entries': total_entries - expired_entries,
            'expired_entries': expired_entries
        }