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
from typing import Any, Union, Literal, get_origin, get_args, get_type_hints, Callable, Dict, Optional, Set


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


def fix_array_schemas(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively fix array schemas by adding a missing 'items' attribute.

    Ensures compatibility with strict OpenAI-style function-calling providers
    which require array types to specify the type of items they contain. Also
    normalises nested ``properties``, ``items``, ``additionalProperties`` and
    ``anyOf``/``oneOf``/``allOf`` schema constructs. The original is not mutated.

    Args:
        schema: The schema dictionary to fix

    Returns:
        dict: The fixed schema
    """
    if not isinstance(schema, dict):
        return schema

    fixed_schema = schema.copy()

    if fixed_schema.get("type") == "array" and "items" not in fixed_schema:
        fixed_schema["items"] = {"type": "string"}

    if "properties" in fixed_schema and isinstance(fixed_schema["properties"], dict):
        fixed_properties = {}
        for prop_name, prop_schema in fixed_schema["properties"].items():
            if isinstance(prop_schema, dict):
                fixed_properties[prop_name] = fix_array_schemas(prop_schema)
            else:
                fixed_properties[prop_name] = prop_schema
        fixed_schema["properties"] = fixed_properties

    if "items" in fixed_schema and isinstance(fixed_schema["items"], dict):
        fixed_schema["items"] = fix_array_schemas(fixed_schema["items"])

    if isinstance(fixed_schema.get("additionalProperties"), dict):
        fixed_schema["additionalProperties"] = fix_array_schemas(
            fixed_schema["additionalProperties"]
        )

    for key in ("anyOf", "oneOf", "allOf"):
        if key in fixed_schema and isinstance(fixed_schema[key], list):
            fixed_schema[key] = [fix_array_schemas(s) for s in fixed_schema[key]]

    return fixed_schema


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


def _parse_docstring_args(docstring: Optional[str]) -> Dict[str, str]:
    """Parse a docstring's ``Args:`` section into {param_name: description}."""
    import re

    param_descriptions: Dict[str, str] = {}
    if not docstring:
        return param_descriptions

    param_section = re.split(r'\s*Args:\s*', docstring)
    if len(param_section) > 1:
        for line in param_section[1].split('\n'):
            line = line.strip()
            if line and ':' in line:
                param_name, param_desc = line.split(':', 1)
                param_descriptions[param_name.strip()] = param_desc.strip()
    return param_descriptions


def build_tool_definition(
    func: Callable,
    function_name: Optional[str] = None,
    *,
    fix_array_items: bool = True,
) -> Optional[Dict[str, Any]]:
    """Build an OpenAI-style tool definition from a callable.

    Single source of truth for signature introspection, docstring ``Args:``
    description parsing, the Python->JSON-schema type map and the recursive
    array-``items`` normalisation. Consolidates the previously triplicated
    ``_generate_tool_definition`` implementations in ``agent.py``, ``llm.py`` and
    ``openai_client.py``.

    Args:
        func: The callable (or Langchain/CrewAI tool class) to introspect.
        function_name: Optional explicit tool name; defaults to ``func.__name__``.
        fix_array_items: When True, arrays missing ``items`` are normalised so
            strict providers accept them (the canonical, complete behaviour).

    Returns:
        dict: The tool definition, or None if ``func`` is not callable.
    """
    # Unwrap Langchain and CrewAI tool classes
    if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
        original_func = func
        func = func.run
        function_name = function_name or original_func.__name__
    elif inspect.isclass(func) and hasattr(func, '_run'):
        original_func = func
        func = func._run
        function_name = function_name or original_func.__name__

    if not callable(func):
        return None

    if function_name is None:
        function_name = getattr(func, '__name__', 'unknown')

    sig = inspect.signature(func)

    docstring = inspect.getdoc(func)
    param_descriptions = _parse_docstring_args(docstring)

    # Resolve type hints once; fall back to raw annotations if resolution fails
    try:
        hints = get_type_hints(func) if getattr(func, "__annotations__", None) else {}
    except (NameError, TypeError, AttributeError):
        hints = getattr(func, "__annotations__", {}) or {}

    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": []
    }

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = hints.get(
            name,
            param.annotation if param.annotation != inspect.Parameter.empty else str
        )
        try:
            prop_schema = annotation_to_json_schema(annotation)
        except Exception as e:
            logging.debug(f"Could not generate schema for {function_name}.{name}: {e}")
            prop_schema = {"type": "string"}

        if name in param_descriptions:
            prop_schema["description"] = param_descriptions[name]

        parameters["properties"][name] = prop_schema

        if get_parameter_requirements(sig, name):
            parameters["required"].append(name)

    if fix_array_items:
        parameters = fix_array_schemas(parameters)

    description = docstring.split('\n')[0] if docstring else f"Function {function_name}"

    return {
        "type": "function",
        "function": {
            "name": function_name,
            "description": description,
            "parameters": parameters
        }
    }