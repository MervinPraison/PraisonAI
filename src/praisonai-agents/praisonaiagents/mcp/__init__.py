"""
Model Context Protocol (MCP) integration for PraisonAI Agents.

This package provides classes and utilities for connecting to MCP servers
using different transport methods:
- stdio: Standard input/output (subprocess)
- sse: Server-Sent Events (legacy HTTP+SSE)
- http_stream: Streamable HTTP (current standard)
- websocket: WebSocket (SEP-1288)

Protocol Revision: 2025-11-25
"""
from .mcp import MCP

# Lazy imports for optional components
def __getattr__(name):
    """Lazy import for optional modules."""
    if name == "WebSocketMCPClient":
        from .mcp_websocket import WebSocketMCPClient
        return WebSocketMCPClient
    elif name == "SessionManager":
        from .mcp_session import SessionManager
        return SessionManager
    elif name == "SecurityConfig":
        from .mcp_security import SecurityConfig
        return SecurityConfig
    elif name == "BaseTransport":
        from .mcp_transport import BaseTransport
        return BaseTransport
    elif name == "TransportConfig":
        from .mcp_transport import TransportConfig
        return TransportConfig
    elif name == "ToolsMCPServer":
        from .mcp_server import ToolsMCPServer
        return ToolsMCPServer
    elif name == "launch_tools_mcp_server":
        from .mcp_server import launch_tools_mcp_server
        return launch_tools_mcp_server
    elif name == "function_to_mcp_schema":
        from .mcp_utils import function_to_mcp_schema
        return function_to_mcp_schema
    elif name == "get_tool_metadata":
        from .mcp_utils import get_tool_metadata
        return get_tool_metadata
    elif name == "python_type_to_json_schema":
        from .mcp_utils import python_type_to_json_schema
        return python_type_to_json_schema
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Client
    "MCP",
    # Server (lazy loaded)
    "ToolsMCPServer",
    "launch_tools_mcp_server",
    # Utilities (lazy loaded)
    "function_to_mcp_schema",
    "get_tool_metadata",
    "python_type_to_json_schema",
    # Transport components (lazy loaded)
    "WebSocketMCPClient",
    "SessionManager",
    "SecurityConfig",
    "BaseTransport",
    "TransportConfig",
]
