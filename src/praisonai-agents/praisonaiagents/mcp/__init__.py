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
from .._lazy import create_lazy_getattr

# Lazy imports for optional components
_LAZY_IMPORTS = {
    "WebSocketMCPClient": ("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPClient"),
    "SessionManager": ("praisonaiagents.mcp.mcp_session", "SessionManager"),
    "SecurityConfig": ("praisonaiagents.mcp.mcp_security", "SecurityConfig"),
    "BaseTransport": ("praisonaiagents.mcp.mcp_transport", "BaseTransport"),
    "TransportConfig": ("praisonaiagents.mcp.mcp_transport", "TransportConfig"),
    "ToolsMCPServer": ("praisonaiagents.mcp.mcp_server", "ToolsMCPServer"),
    "launch_tools_mcp_server": ("praisonaiagents.mcp.mcp_server", "launch_tools_mcp_server"),
    "function_to_mcp_schema": ("praisonaiagents.mcp.mcp_utils", "function_to_mcp_schema"),
    "get_tool_metadata": ("praisonaiagents.mcp.mcp_utils", "get_tool_metadata"),
    "python_type_to_json_schema": ("praisonaiagents.mcp.mcp_utils", "python_type_to_json_schema"),
    "fix_array_schemas": ("praisonaiagents.mcp.mcp_schema_utils", "fix_array_schemas"),
    "ThreadLocalEventLoop": ("praisonaiagents.mcp.mcp_schema_utils", "ThreadLocalEventLoop"),
    "get_thread_local_event_loop": ("praisonaiagents.mcp.mcp_schema_utils", "get_thread_local_event_loop"),
    # Auth storage (lazy loaded)
    # NOTE: the (module, attribute) tuples below are import targets, not
    # credentials; the trailing pragma silences GitGuardian's generic
    # "Authentication Tuple" false positive on the auth/oauth string pairs.
    "MCPAuthStorage": ("praisonaiagents.mcp.mcp_auth_storage", "MCPAuthStorage"),  # pragma: allowlist secret
    "get_default_auth_filepath": ("praisonaiagents.mcp.mcp_auth_storage", "get_default_auth_filepath"),  # pragma: allowlist secret
    # OAuth callback utilities (lazy loaded)
    "OAuthCallbackHandler": ("praisonaiagents.mcp.mcp_oauth_callback", "OAuthCallbackHandler"),  # pragma: allowlist secret
    "generate_state": ("praisonaiagents.mcp.mcp_oauth_callback", "generate_state"),
    "generate_code_verifier": ("praisonaiagents.mcp.mcp_oauth_callback", "generate_code_verifier"),
    "generate_code_challenge": ("praisonaiagents.mcp.mcp_oauth_callback", "generate_code_challenge"),
    "get_redirect_url": ("praisonaiagents.mcp.mcp_oauth_callback", "get_redirect_url"),
    "OAUTH_CALLBACK_PORT": ("praisonaiagents.mcp.mcp_oauth_callback", "OAUTH_CALLBACK_PORT"),
    "OAUTH_CALLBACK_PATH": ("praisonaiagents.mcp.mcp_oauth_callback", "OAUTH_CALLBACK_PATH"),  # pragma: allowlist secret
    # Protocols (lazy loaded)
    "MCPClientProtocol": ("praisonaiagents.mcp.protocols", "MCPClientProtocol"),
    # Loader (lazy loaded)
    "load_mcp_tools": ("praisonaiagents.mcp.loader", "load_mcp_tools"),
    # Resource/prompt normalisation helpers (lazy loaded)
    "normalize_resource_result": ("praisonaiagents.mcp.resources", "normalize_resource_result"),
    "normalize_prompt_result": ("praisonaiagents.mcp.resources", "normalize_prompt_result"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)

__all__ = [
    # Client
    "MCP",
    # Protocols (lazy loaded)
    "MCPClientProtocol",
    # Loader (lazy loaded)
    "load_mcp_tools",
    # Resource/prompt normalisation helpers (lazy loaded)
    "normalize_resource_result",
    "normalize_prompt_result",
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
