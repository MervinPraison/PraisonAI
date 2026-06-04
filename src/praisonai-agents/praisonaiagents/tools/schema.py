"""JSON Schema generation utilities for tool parameters.

This module provides a shared utility for converting Python type annotations
to JSON Schema format. It handles complex types like Optional, Union, Literal,
and Enum that were previously collapsed to simple "string" types.

Usage:
    from praisonaiagents.tools.schema import annotation_to_json_schema
    
    schema = annotation_to_json_schema(Optional[int])
    # {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    
    schema = annotation_to_json_schema(Literal["fast", "deep"])
    # {"type": "string", "enum": ["fast", "deep"]}
"""

import enum
import inspect
from typing import Any, Union, Literal, get_origin, get_args


def annotation_to_json_schema(annotation: Any) -> dict:
    """Convert Python type annotation to JSON Schema format.
    
    Handles:
    - Basic types (str, int, float, bool)
    - Optional[T] -> {"anyOf": [T schema, {"type": "null"}]}
    - Union[T1, T2] -> {"anyOf": [T1 schema, T2 schema]}
    - Literal["a", "b"] -> {"type": "string", "enum": ["a", "b"]}
    - Enum subclasses -> {"type": "string", "enum": [e.value for e in MyEnum]}
    - List[T] -> {"type": "array", "items": T schema}
    - Dict[K, V] -> {"type": "object", "additionalProperties": V schema}
    
    Args:
        annotation: Python type annotation to convert
        
    Returns:
        dict: JSON Schema representation
    """
    # Handle None type
    if annotation is type(None):
        return {"type": "null"}
    
    # Get typing origin and args
    origin = get_origin(annotation)
    args = get_args(annotation)
    
    # Handle Union types (including Optional[T] which is Union[T, None])
    if origin is Union:
        schemas = [annotation_to_json_schema(arg) for arg in args]
        
        # Check if this is Optional[T] (Union[T, None])
        null_schemas = [s for s in schemas if s == {"type": "null"}]
        non_null_schemas = [s for s in schemas if s != {"type": "null"}]
        
        if null_schemas and len(non_null_schemas) == 1:
            # This is Optional[T] - simplified format
            return {"anyOf": [non_null_schemas[0], {"type": "null"}]}
        else:
            # General Union type
            return {"anyOf": schemas}
    
    # Handle Literal types
    if origin is Literal or (hasattr(annotation, '__origin__') and 
                           str(annotation.__origin__).endswith('Literal')):
        return {"type": "string", "enum": list(args)}
    
    # Handle Enum subclasses
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {"type": "string", "enum": [e.value for e in annotation]}
    
    # Handle List types
    if origin is list:
        if args:
            items_schema = annotation_to_json_schema(args[0])
            return {"type": "array", "items": items_schema}
        else:
            return {"type": "array"}
    
    # Handle Dict types
    if origin is dict:
        if len(args) >= 2:
            value_schema = annotation_to_json_schema(args[1])
            return {"type": "object", "additionalProperties": value_schema}
        else:
            return {"type": "object"}
    
    # Handle basic types
    type_map = {
        str: "string",
        int: "integer", 
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null"
    }
    
    return {"type": type_map.get(annotation, "string")}


def get_parameter_requirements(sig: inspect.Signature, param_name: str) -> bool:
    """Determine if a parameter is required based on its signature.
    
    A parameter is required if it has no default value, unless it's Optional.
    
    Args:
        sig: Function signature
        param_name: Parameter name to check
        
    Returns:
        bool: True if parameter is required
    """
    param = sig.parameters.get(param_name)
    if not param:
        return False
    
    # Parameter with default is not required
    if param.default is not inspect.Parameter.empty:
        return False
    
    # Check if the type annotation indicates optional
    if param.annotation is not inspect.Parameter.empty:
        origin = get_origin(param.annotation)
        if origin is Union:
            args = get_args(param.annotation)
            # Optional[T] is Union[T, None]
            if type(None) in args:
                return False
    
    # No default and not optional = required
    return True