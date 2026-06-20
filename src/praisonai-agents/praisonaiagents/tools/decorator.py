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
import copy
from typing import Any, Callable, Dict, Optional, Union, get_type_hints

from .base import BaseTool
from .schema import annotation_to_json_schema, get_parameter_requirements, build_parameters_schema

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
        version: str = "1.0.0",
        availability: Optional[Callable[[], tuple[bool, str]]] = None,
        dynamic_schema_overrides: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        retry_policy: Optional[Any] = None
    ):
        self._func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or f"Tool: {self.name}"
        self.version = version
        self._availability = availability
        self._schema_override = dynamic_schema_overrides
        self.retry_policy = retry_policy
        
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
        try:
            sig = inspect.signature(func)
            hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        except (ValueError, NameError, Exception) as e:
            # Handle built-ins, forward references, and other signature/type issues
            logging.debug(f"Could not generate schema for {func.__name__}: {e}")
            return {"type": "object", "properties": {}, "required": []}
        
        # Use the new shared helper with a predicate for injected parameters
        return build_parameters_schema(
            sig,
            hints,
            skip={"self", "cls"},
            skip_predicate=lambda name, ptype: name in self._injected_params or is_injected_type(ptype),
            func_name=func.__name__
        )
    
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
    
    def get_schema(self) -> Dict[str, Any]:
        """Get OpenAI-compatible function schema for this tool.
        
        Applies dynamic schema overrides if present.
        """
        # Build base schema directly to avoid double override from parent
        base_schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": copy.deepcopy(self.parameters)
            }
        }
        
        # Apply dynamic override if present
        if self._schema_override is not None:
            try:
                return self._schema_override(base_schema)
            except Exception as e:
                logging.warning(f"Dynamic schema override failed for tool '{self.name}': {e}")
                return base_schema
        
        return base_schema
    
    def check_availability(self) -> tuple[bool, str]:
        """Check if this tool is currently available to run.
        
        Returns:
            tuple of (is_available, reason_if_not)
        """
        if self._availability:
            try:
                return self._availability()
            except Exception as e:
                logging.warning(f"Tool {self.name} availability check failed: {e}")
                return False, f"Availability check failed: {e}"
        # Default: always available if no check function provided
        return True, ""


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "1.0.0",
    availability: Optional[Callable[[], tuple[bool, str]]] = None,
    dynamic_schema_overrides: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    retry_policy: Optional[Any] = None
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
            
        @tool(availability=lambda: (bool(os.getenv("API_KEY")), "API_KEY missing"))
        def my_func(x: str) -> str:
            return x
            
        @tool(retry_policy=RetryPolicy(max_attempts=5))
        def my_func(x: str) -> str:
            return x
    
    Args:
        func: The function to wrap (when used without parentheses)
        name: Override the tool name (default: function name)
        description: Override description (default: function docstring)
        version: Tool version (default: "1.0.0")
        availability: Function that returns (is_available, reason) tuple
        dynamic_schema_overrides: Function to dynamically modify tool schema at runtime
        retry_policy: RetryPolicy for tool execution with exponential backoff
    
    Returns:
        FunctionTool instance that wraps the function
    """
    def decorator(fn: Callable) -> FunctionTool:
        tool_instance = FunctionTool(
            func=fn,
            name=name,
            description=description,
            version=version,
            availability=availability,
            dynamic_schema_overrides=dynamic_schema_overrides,
            retry_policy=retry_policy
        )
        
        # Validate the tool at creation time for early error detection
        try:
            tool_instance.validate()
            tool_instance.validate_schema_roundtrip()
        except Exception as e:
            logging.warning(f"Tool validation warning for {tool_instance.name}: {e}")
        
        # Register with global registry if available
        # Note: Don't pass dynamic_schema_overrides again since FunctionTool already handles it
        try:
            logging.debug(f"Attempting to import registry for tool {tool_instance.name}")
            from praisonaiagents.tools.registry import get_registry
            logging.debug("Successfully imported get_registry")
            registry = get_registry()
            logging.debug(f"Got registry: {registry}, type: {type(registry)}")
            if registry:
                logging.debug(f"Registering tool {tool_instance.name}")
                registry.register(tool_instance)
                logging.debug(f"Tool {tool_instance.name} registered successfully")
            else:
                logging.warning(f"Registry is None for tool {tool_instance.name}")
        except ImportError as e:
            logging.warning(f"Import error during registration: {e}")
        except Exception as e:
            logging.warning(f"Failed to register tool {tool_instance.name}: {e}")
        
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
    
    try:
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
    except (ValueError, NameError, Exception) as e:
        # Handle built-ins, forward references, and other signature/type issues
        logging.debug(f"Could not generate schema for {name}: {e}")
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description.strip(),
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }
    
    # Detect and skip injected parameters (same as FunctionTool)
    injected_params = get_injected_params(func)
    
    # Use the new shared helper with injected parameter filtering
    parameters = build_parameters_schema(
        sig,
        hints,
        skip={"self"},
        skip_predicate=lambda name, ptype: name in injected_params or is_injected_type(ptype),
        func_name=name
    )
    
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description.strip(),
            "parameters": parameters
        }
    }
