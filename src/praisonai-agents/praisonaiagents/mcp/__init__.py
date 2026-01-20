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
    elif name == "fix_array_schemas":
        from .mcp_schema_utils import fix_array_schemas
        return fix_array_schemas
    elif name == "ThreadLocalEventLoop":
        from .mcp_schema_utils import ThreadLocalEventLoop
        return ThreadLocalEventLoop
    elif name == "get_thread_local_event_loop":
        from .mcp_schema_utils import get_thread_local_event_loop
        return get_thread_local_event_loop
    # Auth storage (lazy loaded)
    elif name == "MCPAuthStorage":
        from .mcp_auth_storage import MCPAuthStorage
        return MCPAuthStorage
    elif name == "get_default_auth_filepath":
        from .mcp_auth_storage import get_default_auth_filepath
        return get_default_auth_filepath
    # OAuth callback utilities (lazy loaded)
    elif name == "OAuthCallbackHandler":
        from .mcp_oauth_callback import OAuthCallbackHandler
        return OAuthCallbackHandler
    elif name == "generate_state":
        from .mcp_oauth_callback import generate_state
        return generate_state
    elif name == "generate_code_verifier":
        from .mcp_oauth_callback import generate_code_verifier
        return generate_code_verifier
    elif name == "generate_code_challenge":
        from .mcp_oauth_callback import generate_code_challenge
        return generate_code_challenge
    elif name == "get_redirect_url":
        from .mcp_oauth_callback import get_redirect_url
        return get_redirect_url
    elif name == "OAUTH_CALLBACK_PORT":
        from .mcp_oauth_callback import OAUTH_CALLBACK_PORT
        return OAUTH_CALLBACK_PORT
    elif name == "OAUTH_CALLBACK_PATH":
        from .mcp_oauth_callback import OAUTH_CALLBACK_PATH
        return OAUTH_CALLBACK_PATH
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
    # Schema utilities (lazy loaded)
    "fix_array_schemas",
    "ThreadLocalEventLoop",
    "get_thread_local_event_loop",
    # Transport components (lazy loaded)
    "WebSocketMCPClient",
    "SessionManager",
    "SecurityConfig",
    "BaseTransport",
    "TransportConfig",
    # Auth storage (lazy loaded)
    "MCPAuthStorage",
    "get_default_auth_filepath",
    # OAuth callback utilities (lazy loaded)
    "OAuthCallbackHandler",
    "generate_state",
    "generate_code_verifier",
    "generate_code_challenge",
    "get_redirect_url",
    "OAUTH_CALLBACK_PORT",
    "OAUTH_CALLBACK_PATH",
]
