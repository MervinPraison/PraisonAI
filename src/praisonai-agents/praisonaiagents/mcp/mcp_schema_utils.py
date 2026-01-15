"""
MCP Schema Utilities.

This module provides shared schema manipulation utilities for MCP transports.
These utilities ensure compatibility with OpenAI's function calling format
and other LLM providers.

DRY: This module centralizes schema fixing logic that was previously
duplicated across mcp.py, mcp_sse.py, mcp_http_stream.py, and mcp_websocket.py.
"""

import threading
from typing import Any, Dict, Optional


def fix_array_schemas(schema: Any) -> Any:
    """
    Fix array schemas by adding missing 'items' attribute required by OpenAI.
    
    This ensures compatibility with OpenAI's function calling format which
    requires array types to specify the type of items they contain.
    
    Args:
        schema: The schema dictionary to fix
        
    Returns:
        dict: The fixed schema with 'items' added to array types
        
    Example:
        >>> schema = {"type": "array"}
        >>> fixed = fix_array_schemas(schema)
        >>> fixed
        {'type': 'array', 'items': {'type': 'string'}}
    """
    if not isinstance(schema, dict):
        return schema
        
    # Create a copy to avoid modifying the original
    fixed_schema = schema.copy()
    
    # Fix array types at the current level
    if fixed_schema.get("type") == "array" and "items" not in fixed_schema:
        # Add a default items schema for arrays without it
        fixed_schema["items"] = {"type": "string"}
        
    # Recursively fix nested schemas
    if "properties" in fixed_schema:
        fixed_properties = {}
        for prop_name, prop_schema in fixed_schema["properties"].items():
            fixed_properties[prop_name] = fix_array_schemas(prop_schema)
        fixed_schema["properties"] = fixed_properties
        
    # Fix items schema if it exists
    if "items" in fixed_schema:
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


class ThreadLocalEventLoop:
    """
    Thread-local event loop storage for MCP transports.
    
    This class provides thread-safe event loop management, ensuring that
    multiple MCP instances don't share the same event loop, which could
    cause race conditions.
    
    Usage:
        event_loop_manager = ThreadLocalEventLoop()
        loop = event_loop_manager.get_loop()
        # Use loop for async operations
        event_loop_manager.cleanup()
    """
    
    def __init__(self):
        """Initialize thread-local storage."""
        self._local = threading.local()
        self._lock = threading.Lock()
    
    def get_loop(self):
        """
        Get or create an event loop for the current thread.
        
        Returns:
            asyncio.AbstractEventLoop: Event loop for current thread
        """
        import asyncio
        
        # Check if we have a loop for this thread
        loop = getattr(self._local, 'loop', None)
        
        if loop is None or loop.is_closed():
            with self._lock:
                # Double-check after acquiring lock
                loop = getattr(self._local, 'loop', None)
                if loop is None or loop.is_closed():
                    loop = asyncio.new_event_loop()
                    self._local.loop = loop
        
        return loop
    
    def set_loop(self, loop):
        """
        Set the event loop for the current thread.
        
        Args:
            loop: The event loop to set
        """
        self._local.loop = loop
    
    def cleanup(self):
        """Clean up the event loop for the current thread."""
        loop = getattr(self._local, 'loop', None)
        if loop is not None and not loop.is_closed():
            try:
                loop.close()
            except Exception:
                pass
        self._local.loop = None


# Singleton instance for backward compatibility with existing code
# that uses get_event_loop() function pattern
_default_event_loop_manager = ThreadLocalEventLoop()


def get_thread_local_event_loop():
    """
    Get or create a thread-local event loop.
    
    This is a drop-in replacement for the global get_event_loop() functions
    in the transport modules, providing thread safety.
    
    Returns:
        asyncio.AbstractEventLoop: Event loop for current thread
    """
    return _default_event_loop_manager.get_loop()


def json_type_to_python_type(json_type: str) -> type:
    """
    Convert JSON Schema type to Python type annotation.
    
    Args:
        json_type: JSON Schema type string
        
    Returns:
        Python type corresponding to the JSON type
    """
    type_map = {
        'string': str,
        'integer': int,
        'number': float,
        'boolean': bool,
        'array': list,
        'object': dict,
        'null': type(None),
    }
    return type_map.get(json_type, str)


def extract_schema_properties(input_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract properties and required fields from an input schema.
    
    Args:
        input_schema: JSON Schema for tool input
        
    Returns:
        Dictionary with 'properties' and 'required' keys
    """
    if not input_schema:
        return {'properties': {}, 'required': []}
    
    return {
        'properties': input_schema.get('properties', {}),
        'required': input_schema.get('required', [])
    }
