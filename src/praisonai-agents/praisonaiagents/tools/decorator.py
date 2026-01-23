"""Tool decorator for converting functions into tools.

This module provides the @tool decorator for easily creating tools from functions.

Usage:
    from praisonaiagents import tool

    @tool
    def search(query: str) -> list:
        '''Search the web for information.'''
        return [...]

    # Or with explicit parameters:
    @tool(name="web_search", description="Search the internet")
    def search(query: str, max_results: int = 5) -> list:
        return [...]
    
    # With injected state:
    from praisonaiagents.tools import Injected
    
    @tool
    def my_tool(query: str, state: Injected[dict]) -> str:
        '''Tool with injected state.'''
        return f"session={state.get('session_id')}"
"""

import inspect
import functools
import logging
from typing import Any, Callable, Dict, Optional, Union, get_type_hints

from .base import BaseTool

# Lazy load injected module functions to reduce import time
_injected_module = None

def _get_injected_module():
    """Lazy load the injected module."""
    global _injected_module
    if _injected_module is None:
        from . import injected as _inj
        _injected_module = _inj
    return _injected_module

def is_injected_type(annotation):
    return _get_injected_module().is_injected_type(annotation)

def get_injected_params(func):
    return _get_injected_module().get_injected_params(func)

def inject_state_into_kwargs(kwargs, injected_params):
    return _get_injected_module().inject_state_into_kwargs(kwargs, injected_params)

def filter_injected_from_schema(schema, func):
    return _get_injected_module().filter_injected_from_schema(schema, func)


class FunctionTool(BaseTool):
    """A BaseTool wrapper for plain functions.
    
    Created automatically by the @tool decorator.
    Supports Injected[T] parameters for state injection.
    """
    
    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        version: str = "1.0.0"
    ):
        self._func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or f"Tool: {self.name}"
        self.version = version
        
        # Detect injected parameters
        self._injected_params = get_injected_params(func)
        
        # Generate schema from the original function, not run()
        self.parameters = self._generate_schema_from_func(func)
        
        # Copy function metadata
        functools.update_wrapper(self, func)
        
        # Skip parent's schema generation since we already did it
        # Just set defaults that parent would set
        if not self.name:
            self.name = self.__class__.__name__.lower().replace("tool", "")
        if not self.description:
            self.description = self.__class__.__doc__ or f"Tool: {self.name}"
    
    @property
    def injected_params(self) -> Dict[str, Any]:
        """Get the injected parameters for this tool."""
        return self._injected_params
    
    def _generate_schema_from_func(self, func: Callable) -> Dict[str, Any]:
        """Generate JSON Schema from the wrapped function's signature.
        
        Injected parameters are excluded from the schema.
        """
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        try:
            sig = inspect.signature(func)
            hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
            
            for param_name, param in sig.parameters.items():
                if param_name in ('self', 'cls'):
                    continue
                
                # Skip injected parameters - they don't go in schema
                if param_name in self._injected_params:
                    continue
                
                # Get type hint
                param_type = hints.get(param_name, Any)
                
                # Double-check it's not an Injected type
                if is_injected_type(param_type):
                    continue
                
                json_type = BaseTool._python_type_to_json(param_type)
                
                schema["properties"][param_name] = {"type": json_type}
                
                # Check if required (no default value)
                if param.default is inspect.Parameter.empty:
                    schema["required"].append(param_name)
        except Exception as e:
            logging.debug(f"Could not generate schema for {func.__name__}: {e}")
        
        return schema
    
    def run(self, **kwargs) -> Any:
        """Execute the wrapped function with injected state."""
        # Inject state for any Injected parameters
        kwargs = inject_state_into_kwargs(kwargs, self._injected_params)
        return self._func(**kwargs)
    
    def __call__(self, *args, **kwargs) -> Any:
        """Allow calling with positional args like the original function.
        
        Injects state for Injected parameters.
        """
        # Inject state for any Injected parameters
        kwargs = inject_state_into_kwargs(kwargs, self._injected_params)
        return self._func(*args, **kwargs)


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "1.0.0"
) -> Union[FunctionTool, Callable[[Callable], FunctionTool]]:
    """Decorator to convert a function into a tool.
    
    Can be used with or without arguments:
    
        @tool
        def my_func(x: str) -> str:
            '''Does something.'''
            return x
        
        @tool(name="custom_name", description="Custom description")
        def my_func(x: str) -> str:
            return x
    
    Args:
        func: The function to wrap (when used without parentheses)
        name: Override the tool name (default: function name)
        description: Override description (default: function docstring)
        version: Tool version (default: "1.0.0")
    
    Returns:
        FunctionTool instance that wraps the function
    """
    def decorator(fn: Callable) -> FunctionTool:
        tool_instance = FunctionTool(
            func=fn,
            name=name,
            description=description,
            version=version
        )
        
        # Register with global registry if available
        try:
            from .registry import get_registry
            registry = get_registry()
            if registry:
                registry.register(tool_instance)
        except ImportError:
            pass  # Registry not yet available
        
        return tool_instance
    
    # Handle both @tool and @tool(...) syntax
    if func is not None:
        # Called without parentheses: @tool
        return decorator(func)
    else:
        # Called with parentheses: @tool(...) 
        return decorator


def is_tool(obj: Any) -> bool:
    """Check if an object is a tool (BaseTool instance or decorated function)."""
    if isinstance(obj, BaseTool):
        return True
    if isinstance(obj, FunctionTool):
        return True
    # Check for tools created by other frameworks
    if hasattr(obj, 'run') and hasattr(obj, 'name'):
        return True
    return False


def get_tool_schema(obj: Any) -> Optional[Dict[str, Any]]:
    """Get OpenAI-compatible schema for any tool-like object.
    
    Supports:
    - BaseTool instances
    - FunctionTool instances  
    - Plain functions (generates schema from signature)
    - LangChain tools
    - CrewAI tools
    """
    # BaseTool or FunctionTool
    if isinstance(obj, BaseTool):
        return obj.get_schema()
    
    # Plain callable
    if callable(obj):
        return _schema_from_function(obj)
    
    return None


def _schema_from_function(func: Callable) -> Dict[str, Any]:
    """Generate OpenAI function schema from a plain function."""
    name = getattr(func, '__name__', 'unknown')
    description = func.__doc__ or f"Function: {name}"
    
    # Build parameters schema
    properties = {}
    required = []
    
    try:
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            param_type = hints.get(param_name, Any)
            json_type = BaseTool._python_type_to_json(param_type)
            
            properties[param_name] = {"type": json_type}
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
    except Exception as e:
        logging.debug(f"Could not generate schema for {name}: {e}")
    
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description.strip(),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }
