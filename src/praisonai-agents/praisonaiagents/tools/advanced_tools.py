"""Advanced tools framework for PraisonAI Agents.

This module provides advanced tool decorators and functionality including:
- Pre/Post execution hooks
- Tool-level caching with TTL
- External execution markers
- Structured user input fields

Maintains backward compatibility with existing tools.
"""

import asyncio
import functools
import inspect
import time
from typing import Any, Callable, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum


class Priority(Enum):
    """Hook execution priority levels."""
    HIGHEST = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    LOWEST = 5


@dataclass
class ToolContext:
    """Context object passed to hooks and handlers."""
    tool_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    result: Any = None
    error: Optional[Exception] = None
    agent: Any = None  # Will be set by agent at runtime
    execution_time: float = 0.0
    metadata: dict = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    
    def set_result(self, result: Any):
        """Set the tool result and calculate execution time."""
        self.result = result
        self.execution_time = time.time() - self.start_time
    
    def set_error(self, error: Exception):
        """Set the tool error and calculate execution time."""
        self.error = error
        self.execution_time = time.time() - self.start_time


@dataclass
class Hook:
    """Represents a hook function with priority."""
    func: Callable[[ToolContext], Any]
    priority: Priority = Priority.MEDIUM
    
    def __call__(self, context: ToolContext) -> Any:
        return self.func(context)


@dataclass
class CacheConfig:
    """Cache configuration for tools."""
    enabled: bool = True
    ttl: int = 300  # seconds
    backend: str = 'memory'  # 'memory', 'redis', etc.
    key_func: Optional[Callable] = None
    condition: Optional[Callable] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ExternalConfig:
    """External execution configuration."""
    enabled: bool = True
    executor: str = 'default'
    requirements: List[str] = field(default_factory=list)
    estimated_time: int = 60  # seconds
    when: Optional[Callable] = None  # Conditional external execution
    type: str = 'generic'  # 'human_approval', 'webhook', 'generic'
    endpoint: Optional[str] = None
    auth_token: Optional[str] = None


@dataclass
class Field:
    """Structured input field definition."""
    name: str
    type: Any = str
    description: str = ""
    required: bool = True
    default: Any = None
    secret: bool = False
    
    def __post_init__(self):
        if self.default is not None:
            self.required = False


@dataclass
class InputGroup:
    """Group of related input fields."""
    name: str
    fields: List[Field]
    
    def __init__(self, name: str, *fields: Field):
        self.name = name
        self.fields = list(fields)


class Choice:
    """Choice field type."""
    def __init__(self, choices: List[str]):
        self.choices = choices


class Range:
    """Range field type."""
    def __init__(self, min_val: float, max_val: float):
        self.min = min_val
        self.max = max_val


class Pattern:
    """Pattern validation field type."""
    def __init__(self, pattern: str):
        self.pattern = pattern


# Global hooks registry
_global_hooks = {
    'before': [],
    'after': []
}

# Cache storage
_cache_storage = {}
_cache_metadata = {}  # For TTL tracking

# External handlers registry
_external_handlers = {}


def set_global_hooks(before: Optional[Callable] = None, after: Optional[Callable] = None):
    """Set global hooks that apply to all tools."""
    if before:
        _global_hooks['before'].append(Hook(before))
    if after:
        _global_hooks['after'].append(Hook(after))


def clear_global_hooks():
    """Clear all global hooks."""
    _global_hooks['before'].clear()
    _global_hooks['after'].clear()


def register_external_handler(name: str, handler: Callable):
    """Register an external execution handler."""
    _external_handlers[name] = handler


def invalidate_cache(tags: Optional[List[str]] = None, tool_name: Optional[str] = None):
    """Invalidate cache entries by tags or tool name."""
    if tool_name:
        # Remove all cache entries for a specific tool
        keys_to_remove = [k for k in _cache_storage.keys() if k.startswith(f"{tool_name}:")]
        for key in keys_to_remove:
            del _cache_storage[key]
            if key in _cache_metadata:
                del _cache_metadata[key]
    
    if tags:
        # Remove cache entries with specific tags
        keys_to_remove = []
        for key, metadata in _cache_metadata.items():
            if any(tag in metadata.get('tags', []) for tag in tags):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            if key in _cache_storage:
                del _cache_storage[key]
            del _cache_metadata[key]


def clear_all_caches():
    """Clear all cache entries."""
    _cache_storage.clear()
    _cache_metadata.clear()


def get_cache_stats():
    """Get cache statistics."""
    return {
        'total_entries': len(_cache_storage),
        'hits': sum(m.get('hits', 0) for m in _cache_metadata.values()),
        'misses': sum(m.get('misses', 0) for m in _cache_metadata.values())
    }


def _generate_cache_key(tool_name: str, args: tuple, kwargs: dict, key_func: Optional[Callable] = None) -> str:
    """Generate cache key for tool execution."""
    if key_func:
        return f"{tool_name}:{key_func(*args, **kwargs)}"
    else:
        # Simple hash-based key
        import hashlib
        content = f"{args}:{sorted(kwargs.items())}"
        hash_key = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"{tool_name}:{hash_key}"


def _is_cache_valid(key: str) -> bool:
    """Check if cache entry is still valid (not expired)."""
    if key not in _cache_metadata:
        return False
    
    metadata = _cache_metadata[key]
    if 'expires_at' in metadata:
        return time.time() < metadata['expires_at']
    return True


def _execute_hooks(hooks: List[Hook], context: ToolContext) -> bool:
    """Execute hooks in priority order. Returns False if execution should be stopped."""
    # Sort hooks by priority
    sorted_hooks = sorted(hooks, key=lambda h: h.priority.value)
    
    for hook in sorted_hooks:
        try:
            result = hook(context)
            # If hook returns False, stop execution
            if result is False:
                return False
        except Exception as e:
            # Log hook error but continue execution
            print(f"Hook error in {hook.func.__name__}: {e}")
    
    return True


def _handle_external_execution(func: Callable, context: ToolContext, external_config: ExternalConfig) -> Any:
    """Handle external execution of a tool."""
    # Check if external execution is conditional
    if external_config.when and not external_config.when(*context.args, **context.kwargs):
        # Execute normally
        return func(*context.args, **context.kwargs)
    
    # Look for registered external handler
    handler = _external_handlers.get(external_config.executor)
    if handler:
        return handler(func, context, external_config)
    
    # Default external handling
    if external_config.type == 'human_approval':
        response = input(f"External approval required for {context.tool_name}. Proceed? (y/n): ")
        if response.lower() != 'y':
            raise Exception("External execution denied by user")
    
    # Execute the tool normally for now
    return func(*context.args, **context.kwargs)


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    before: Union[Callable, List[Union[Callable, Tuple[Callable, Priority]]], None] = None,
    after: Union[Callable, List[Union[Callable, Tuple[Callable, Priority]]], None] = None,
    cache: Union[bool, CacheConfig, None] = None,
    external: Union[bool, ExternalConfig, None] = None,
    inputs: Optional[List[Union[Field, InputGroup]]] = None,
    require_approval: Optional[str] = None,
    risk_level: Optional[str] = None
):
    """
    Advanced tool decorator with hooks, caching, external execution, and input validation.
    
    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to function docstring)
        before: Pre-execution hooks
        after: Post-execution hooks
        cache: Caching configuration
        external: External execution configuration
        inputs: Structured input field definitions
        require_approval: Backward compatibility with existing approval system
        risk_level: Risk level for approval system
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_description = description or func.__doc__ or "No description available"
        
        # Normalize hooks
        before_hooks = []
        after_hooks = []
        
        if before:
            if callable(before):
                before_hooks.append(Hook(before))
            elif isinstance(before, list):
                for hook in before:
                    if callable(hook):
                        before_hooks.append(Hook(hook))
                    elif isinstance(hook, tuple) and len(hook) == 2:
                        before_hooks.append(Hook(hook[0], hook[1]))
        
        if after:
            if callable(after):
                after_hooks.append(Hook(after))
            elif isinstance(after, list):
                for hook in after:
                    if callable(hook):
                        after_hooks.append(Hook(hook))
                    elif isinstance(hook, tuple) and len(hook) == 2:
                        after_hooks.append(Hook(hook[0], hook[1]))
        
        # Normalize cache config
        cache_config = None
        if cache is True:
            cache_config = CacheConfig()
        elif isinstance(cache, CacheConfig):
            cache_config = cache
        elif isinstance(cache, dict):
            cache_config = CacheConfig(**cache)
        
        # Normalize external config
        external_config = None
        if external is True:
            external_config = ExternalConfig()
        elif isinstance(external, ExternalConfig):
            external_config = external
        elif isinstance(external, dict):
            external_config = ExternalConfig(**external)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = ToolContext(
                tool_name=tool_name,
                args=args,
                kwargs=kwargs
            )
            
            try:
                # Execute global before hooks
                if not _execute_hooks(_global_hooks['before'], context):
                    return context.result
                
                # Execute tool-specific before hooks
                if not _execute_hooks(before_hooks, context):
                    return context.result
                
                # Check cache
                if cache_config and cache_config.enabled:
                    cache_key = _generate_cache_key(tool_name, args, kwargs, cache_config.key_func)
                    
                    if cache_key in _cache_storage and _is_cache_valid(cache_key):
                        # Cache hit
                        result = _cache_storage[cache_key]
                        _cache_metadata[cache_key]['hits'] = _cache_metadata[cache_key].get('hits', 0) + 1
                        context.set_result(result)
                        
                        # Execute after hooks with cached result
                        _execute_hooks(after_hooks, context)
                        _execute_hooks(_global_hooks['after'], context)
                        
                        return result
                    else:
                        # Cache miss
                        if cache_key in _cache_metadata:
                            _cache_metadata[cache_key]['misses'] = _cache_metadata[cache_key].get('misses', 0) + 1
                        else:
                            _cache_metadata[cache_key] = {'misses': 1, 'hits': 0}
                
                # Execute tool
                if external_config and external_config.enabled:
                    result = _handle_external_execution(func, context, external_config)
                else:
                    result = func(*args, **kwargs)
                
                context.set_result(result)
                
                # Store in cache if configured
                if cache_config and cache_config.enabled:
                    # Check condition if specified
                    if not cache_config.condition or cache_config.condition(result):
                        cache_key = _generate_cache_key(tool_name, args, kwargs, cache_config.key_func)
                        _cache_storage[cache_key] = result
                        
                        # Set expiration
                        if cache_key not in _cache_metadata:
                            _cache_metadata[cache_key] = {'hits': 0, 'misses': 0}
                        
                        _cache_metadata[cache_key].update({
                            'expires_at': time.time() + cache_config.ttl,
                            'tags': cache_config.tags
                        })
                
                # Execute after hooks
                _execute_hooks(after_hooks, context)
                _execute_hooks(_global_hooks['after'], context)
                
                return result
                
            except Exception as e:
                context.set_error(e)
                
                # Execute error handling hooks
                _execute_hooks(after_hooks, context)
                _execute_hooks(_global_hooks['after'], context)
                
                # If error was cleared by hooks, return the result
                if context.error is None:
                    return context.result
                
                # Re-raise the error
                raise e
        
        # Add metadata to the function
        wrapper._tool_metadata = {
            'name': tool_name,
            'description': tool_description,
            'cache_config': cache_config,
            'external_config': external_config,
            'inputs': inputs,
            'before_hooks': before_hooks,
            'after_hooks': after_hooks,
            'require_approval': require_approval,
            'risk_level': risk_level
        }
        
        # Backward compatibility with existing approval system
        if require_approval or risk_level:
            try:
                from .approval import require_approval as approval_decorator
                if risk_level:
                    wrapper = approval_decorator(risk_level)(wrapper)
                elif require_approval:
                    wrapper = approval_decorator(require_approval)(wrapper)
            except ImportError:
                # Approval system not available
                pass
        
        return wrapper
    
    return decorator


# Convenience decorators for common patterns
def cache(ttl: int = 300, backend: str = 'memory', key: Optional[Callable] = None, 
          condition: Optional[Callable] = None, tags: Optional[List[str]] = None):
    """Convenience decorator for caching."""
    config = CacheConfig(
        ttl=ttl,
        backend=backend,
        key_func=key,
        condition=condition,
        tags=tags or []
    )
    return lambda func: tool(cache=config)(func)


def external(executor: str = 'default', requirements: Optional[List[str]] = None,
             estimated_time: int = 60, when: Optional[Callable] = None,
             type: str = 'generic', endpoint: Optional[str] = None):
    """Convenience decorator for external execution."""
    config = ExternalConfig(
        executor=executor,
        requirements=requirements or [],
        estimated_time=estimated_time,
        when=when,
        type=type,
        endpoint=endpoint
    )
    return lambda func: tool(external=config)(func)


def user_input(*fields: Union[Field, InputGroup]):
    """Convenience decorator for user input validation."""
    return lambda func: tool(inputs=list(fields))(func)


# Export all public classes and functions
__all__ = [
    'tool', 'cache', 'external', 'user_input',
    'Field', 'InputGroup', 'Choice', 'Range', 'Pattern',
    'ToolContext', 'Hook', 'CacheConfig', 'ExternalConfig', 'Priority',
    'set_global_hooks', 'clear_global_hooks', 'register_external_handler',
    'invalidate_cache', 'clear_all_caches', 'get_cache_stats'
]