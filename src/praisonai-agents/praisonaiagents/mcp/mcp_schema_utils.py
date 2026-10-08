"""
MCP Schema Utilities.

This module provides shared schema manipulation utilities for MCP transports.
These utilities ensure compatibility with OpenAI's function calling format
and other LLM providers.

DRY: This module centralizes schema fixing logic that was previously
duplicated across mcp.py, mcp_sse.py, mcp_http_stream.py, and mcp_websocket.py.
"""

import inspect
import keyword
import threading
from typing import Any, Dict, Optional


def fix_array_schemas(schema: Any) -> Any:
    """
    Fix array schemas by adding missing 'items' attribute required by OpenAI.

    Thin wrapper around the single canonical ``fix_array_schemas`` helper in
    ``praisonaiagents.llm.schema_utils``. Kept here for backward compatibility
    with the MCP transports (``mcp_sse``, ``mcp_http_stream``, ``mcp_websocket``)
    that import this symbol directly.

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
    from ..llm.schema_utils import fix_array_schemas as _fix_array_schemas
    return _fix_array_schemas(schema)


def build_openai_tool_dict(name: str, description: str, input_schema: Any) -> Dict[str, Any]:
    """
    Build an OpenAI function-calling tool dict for an MCP tool.

    DRY: This centralizes the OpenAI tool-dict construction (including the
    ``__praisonai_deferrable__`` marker) that was previously duplicated across
    ``mcp_sse``, ``mcp_http_stream``, and ``mcp_websocket``.

    Args:
        name: The tool name
        description: The tool description
        input_schema: JSON Schema for the tool input

    Returns:
        dict: OpenAI function-calling tool dict with array schemas fixed and
        the MCP deferrable marker set.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": fix_array_schemas(input_schema),
        },
        "__praisonai_deferrable__": True,  # Mark MCP tools as deferrable for tool search
    }


_JSON_TYPE_ANNOTATIONS = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def build_tool_signature(input_schema: Optional[Dict[str, Any]]) -> inspect.Signature:
    """
    Build the Python signature of an MCP tool wrapper from its input schema.

    DRY: shared by the stdio, SSE, HTTP-stream, and WebSocket tool wrappers.

    MCP input schemas are JSON Schema, so a property name need not be a valid
    Python parameter name (``from``, ``class``, ``max-results``), and required
    properties may follow optional ones. ``inspect.Parameter`` rejects both,
    which would otherwise abort the whole server connection. Representable
    properties become named parameters, required ones first; the others are
    accepted through a trailing ``**kwargs``, so callers still pass them by
    their original names. The signature is for introspection only: the schema
    sent to the LLM is built from ``input_schema`` itself.

    Args:
        input_schema: JSON Schema for the tool input

    Returns:
        inspect.Signature: Signature describing the tool's arguments
    """
    schema = input_schema if isinstance(input_schema, dict) else {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return inspect.Signature([])
    required = schema.get("required") or []

    required_params = []
    optional_params = []
    has_unnamed = False
    for name, prop_schema in properties.items():
        if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
            has_unnamed = True
            continue
        prop_type = prop_schema.get("type", "string") if isinstance(prop_schema, dict) else "string"
        annotation = _JSON_TYPE_ANNOTATIONS.get(prop_type, Any) if isinstance(prop_type, str) else Any
        is_required = name in required
        param = inspect.Parameter(
            name=name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=inspect.Parameter.empty if is_required else None,
            annotation=annotation,
        )
        (required_params if is_required else optional_params).append(param)

    params = required_params + optional_params
    if has_unnamed:
        taken = {param.name for param in params}
        var_keyword = "kwargs"
        while var_keyword in taken:
            var_keyword = f"_{var_keyword}"
        params.append(inspect.Parameter(var_keyword, inspect.Parameter.VAR_KEYWORD))
    return inspect.Signature(params)


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


def get_running_loop_or_none():
    """
    Return the event loop running in the current thread, or ``None``.

    The SSE, HTTP-stream, and WebSocket tool wrappers are created inside their
    client's ``_async_initialize`` coroutine, so this captures the loop that
    owns the MCP session. Their synchronous ``__call__`` must schedule work on
    that loop: callers such as the agent's tool executor run in other threads,
    where the thread-local loop exists but is not running.

    Returns:
        asyncio.AbstractEventLoop or None: The running loop, if any
    """
    import asyncio

    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
