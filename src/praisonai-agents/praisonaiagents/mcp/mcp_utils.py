"""MCP utility functions for converting Python functions to MCP tool schemas.

This module provides utilities to convert Python functions with type hints
into MCP-compatible tool schemas for exposing as MCP server tools.

Usage:
    from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
    
    def my_tool(query: str, max_results: int = 10) -> str:
        '''Search for information.'''
        return "results"
    
    schema = function_to_mcp_schema(my_tool)
    # Returns MCP-compatible tool schema
"""

import inspect
from typing import Any, Callable, Dict, List, Union, get_type_hints, get_origin, get_args


def python_type_to_json_schema(python_type: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to JSON Schema.
    
    Args:
        python_type: A Python type annotation (e.g., str, int, List[str], Optional[int])
    
    Returns:
        JSON Schema dictionary representing the type
    """
    # Handle None type
    if python_type is None or python_type is type(None):
        return {"type": "null"}
    
    # Handle Any type
    if python_type is Any:
        return {}
    
    # Handle basic types
    type_mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        bytes: {"type": "string"},
    }
    
    if python_type in type_mapping:
        return type_mapping[python_type]
    
    # Handle generic types (List, Dict, Optional, Union)
    origin = get_origin(python_type)
    args = get_args(python_type)
    
    # Handle List[T]
    if origin is list:
        if args:
            return {
                "type": "array",
                "items": python_type_to_json_schema(args[0])
            }
        return {"type": "array", "items": {}}
    
    # Handle Dict[K, V]
    if origin is dict:
        return {"type": "object"}
    
    # Handle Optional[T] (Union[T, None])
    if origin is Union:
        # Filter out None type
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            # Optional[T] case
            return python_type_to_json_schema(non_none_args[0])
        elif len(non_none_args) > 1:
            # Union of multiple types
            return {"oneOf": [python_type_to_json_schema(arg) for arg in non_none_args]}
        return {}
    
    # Handle tuple
    if origin is tuple:
        if args:
            return {
                "type": "array",
                "items": [python_type_to_json_schema(arg) for arg in args]
            }
        return {"type": "array"}
    
    # Handle set
    if origin is set:
        if args:
            return {
                "type": "array",
                "items": python_type_to_json_schema(args[0]),
                "uniqueItems": True
            }
        return {"type": "array", "uniqueItems": True}
    
    # Default to object for unknown types
    return {"type": "object"}


def get_tool_metadata(func: Callable) -> Dict[str, str]:
    """Extract metadata from a function for MCP tool registration.
    
    Checks for custom attributes (__mcp_name__, __mcp_description__) first,
    then falls back to function name and docstring.
    
    Args:
        func: The function to extract metadata from
    
    Returns:
        Dictionary with 'name' and 'description' keys
    """
    # Get name - check for custom attribute first
    name = getattr(func, '__mcp_name__', None) or func.__name__
    
    # Get description - check for custom attribute first
    description = getattr(func, '__mcp_description__', None)
    
    if description is None:
        # Extract from docstring
        docstring = inspect.getdoc(func)
        if docstring:
            # Use first line of docstring as description
            description = docstring.split('\n')[0].strip()
        else:
            # Fall back to function name
            description = name
    
    return {
        "name": name,
        "description": description
    }


def function_to_mcp_schema(func: Callable) -> Dict[str, Any]:
    """Convert a Python function to an MCP tool schema.
    
    This function inspects the function's signature, type hints, and docstring
    to generate a complete MCP-compatible tool schema.
    
    Args:
        func: The function to convert
    
    Returns:
        MCP tool schema dictionary with:
        - name: Tool name
        - description: Tool description
        - inputSchema: JSON Schema for parameters
    
    Example:
        def search(query: str, max_results: int = 10) -> str:
            '''Search the web for information.'''
            return "results"
        
        schema = function_to_mcp_schema(search)
        # {
        #     "name": "search",
        #     "description": "Search the web for information.",
        #     "inputSchema": {
        #         "type": "object",
        #         "properties": {
        #             "query": {"type": "string"},
        #             "max_results": {"type": "integer"}
        #         },
        #         "required": ["query"]
        #     }
        # }
    """
    # Get metadata
    metadata = get_tool_metadata(func)
    
    # Get function signature
    sig = inspect.signature(func)
    
    # Try to get type hints
    try:
        type_hints = get_type_hints(func)
    except Exception:
        type_hints = {}
    
    # Build properties and required list
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        # Skip self, cls, and special parameters
        if param_name in ('self', 'cls'):
            continue
        
        # Skip *args and **kwargs
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        
        # Get type annotation
        param_type = type_hints.get(param_name, param.annotation)
        
        if param_type is inspect.Parameter.empty:
            # No type annotation - default to string
            properties[param_name] = {"type": "string"}
        else:
            properties[param_name] = python_type_to_json_schema(param_type)
        
        # Check if parameter is required (no default value)
        if param.default is inspect.Parameter.empty:
            # Check if it's Optional type
            origin = get_origin(param_type) if param_type is not inspect.Parameter.empty else None
            args = get_args(param_type) if param_type is not inspect.Parameter.empty else ()
            
            is_optional = origin is Union and type(None) in args
            
            if not is_optional:
                required.append(param_name)
    
    # Build the schema
    schema = {
        "name": metadata["name"],
        "description": metadata["description"],
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }
    
    return schema


def functions_to_mcp_tools(functions: List[Callable]) -> List[Dict[str, Any]]:
    """Convert multiple functions to MCP tool schemas.
    
    Args:
        functions: List of functions to convert
    
    Returns:
        List of MCP tool schemas
    """
    return [function_to_mcp_schema(func) for func in functions]


def filter_disabled_tools(
    tools: List[Dict[str, Any]], 
    disabled_tools: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter out disabled tools from a tool list.
    
    Args:
        tools: List of tool definitions (dicts with 'name' key)
        disabled_tools: List of tool names to disable
        
    Returns:
        Filtered list of tools
    """
    if not disabled_tools:
        return tools
        
    disabled_set = set(disabled_tools)
    return [t for t in tools if t.get("name") not in disabled_set]


def filter_tools_by_allowlist(
    tools: List[Dict[str, Any]], 
    allowed_tools: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter tools to only include those in allowlist.
    
    Args:
        tools: List of tool definitions (dicts with 'name' key)
        allowed_tools: List of tool names to allow (empty = allow all)
        
    Returns:
        Filtered list of tools
    """
    if not allowed_tools:
        return tools
        
    allowed_set = set(allowed_tools)
    return [t for t in tools if t.get("name") in allowed_set]

