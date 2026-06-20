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
import logging
from typing import Any, Union, Literal, get_origin, get_args, Callable, Dict, Optional, Set


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
        # Infer type from literal values if all are the same type
        values = list(args)
        if values:
            types_seen = set(type(v) for v in values)
            if len(types_seen) == 1:
                single_type = next(iter(types_seen))
                type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
                if single_type in type_map:
                    return {"type": type_map[single_type], "enum": values}
        # Mixed types or non-primitive - use enum without type constraint
        return {"enum": values}
    
    # Handle Enum subclasses
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        # Infer type from enum values if all are the same type
        values = [e.value for e in annotation]
        if values:
            types_seen = set(type(v) for v in values)
            if len(types_seen) == 1:
                single_type = next(iter(types_seen))
                type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
                if single_type in type_map:
                    return {"type": type_map[single_type], "enum": values}
        # Mixed types or non-primitive - use enum without type constraint
        return {"enum": values}
    
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


def build_parameters_schema(
    sig: inspect.Signature,
    hints: Dict[str, Any],
    *,
    skip: Optional[Set[str]] = None,
    skip_predicate: Optional[Callable[[str, Any], bool]] = None,
    func_name: str = "unknown"
) -> Dict[str, Any]:
    """Build a JSON Schema for function parameters from signature and type hints.
    
    This is a shared helper that consolidates the duplicate schema generation logic
    previously found in BaseTool, decorator._generate_schema_from_func, and
    decorator._schema_from_function.
    
    Args:
        sig: Function signature from inspect.signature()
        hints: Type hints from typing.get_type_hints()
        skip: Set of parameter names to skip (e.g. {"self", "cls"})
        skip_predicate: Additional predicate to determine if a parameter should be skipped
                       Takes (param_name, param_type) and returns True to skip
        func_name: Function name for error logging
        
    Returns:
        dict: JSON Schema with {"type": "object", "properties": {...}, "required": [...]}
    """
    schema = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    # Default skip set
    if skip is None:
        skip = {"self", "cls"}
    
    for param_name, _param in sig.parameters.items():
        # Skip explicitly excluded parameters
        if param_name in skip:
            continue
        
        # Get type hint
        param_type = hints.get(param_name, Any)
        
        # Apply skip predicate if provided
        if skip_predicate and skip_predicate(param_name, param_type):
            continue
        
        # Use existing annotation_to_json_schema for proper type handling
        try:
            prop_schema = annotation_to_json_schema(param_type)
        except Exception as e:
            # Log but continue - allow partial schemas
            logging.debug(f"Could not generate schema for {func_name}.{param_name}: {e}")
            # Default to string type for parameters that fail schema generation
            prop_schema = {"type": "string"}
        
        schema["properties"][param_name] = prop_schema
        
        # Check if required using existing logic
        if get_parameter_requirements(sig, param_name):
            schema["required"].append(param_name)
    
    return schema