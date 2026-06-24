"""Shared schema utilities for LLM tool calling.

This module provides helpers for normalising tool/function schemas so they are
compatible with OpenAI-style function calling across the LLM, OpenAI client and
MCP code paths.
"""

from typing import Any, Dict


def fix_array_schemas(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively fix array schemas by adding missing 'items' attribute.

    This is the single canonical implementation shared by the LLM, OpenAI client
    and MCP code paths. It ensures compatibility with OpenAI's function calling
    format which requires array types to specify the type of items they contain,
    and normalises nested ``properties``, ``items``, ``additionalProperties`` and
    ``anyOf``/``oneOf``/``allOf`` schema constructs.

    Args:
        schema: The schema dictionary to fix

    Returns:
        dict: The fixed schema (the original is not mutated)
    """
    if not isinstance(schema, dict):
        return schema

    # Create a copy to avoid modifying the original
    fixed_schema = schema.copy()

    # Fix array types at the current level
    if fixed_schema.get("type") == "array" and "items" not in fixed_schema:
        # Add a default items schema for arrays without it
        fixed_schema["items"] = {"type": "string"}

    # Recursively fix nested schemas in properties
    if "properties" in fixed_schema and isinstance(fixed_schema["properties"], dict):
        fixed_properties = {}
        for prop_name, prop_schema in fixed_schema["properties"].items():
            if isinstance(prop_schema, dict):
                fixed_properties[prop_name] = fix_array_schemas(prop_schema)
            else:
                fixed_properties[prop_name] = prop_schema
        fixed_schema["properties"] = fixed_properties

    # Fix items schema if it exists
    if "items" in fixed_schema and isinstance(fixed_schema["items"], dict):
        fixed_schema["items"] = fix_array_schemas(fixed_schema["items"])

    # Fix additionalProperties if it's a schema
    if isinstance(fixed_schema.get("additionalProperties"), dict):
        fixed_schema["additionalProperties"] = fix_array_schemas(
            fixed_schema["additionalProperties"]
        )

    # Fix anyOf/oneOf/allOf schemas
    for key in ("anyOf", "oneOf", "allOf"):
        if key in fixed_schema and isinstance(fixed_schema[key], list):
            fixed_schema[key] = [fix_array_schemas(s) for s in fixed_schema[key]]

    return fixed_schema
