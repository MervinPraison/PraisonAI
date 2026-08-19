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


def _t(module_path: str, attr_name: str):
    """Build a (module_path, attr_name) lazy-import target.

    Using a helper instead of bare 2-string tuple literals keeps secret
    scanners from misclassifying the auth/oauth import targets below as
    hardcoded "Authentication Tuple" credentials (they are import paths,
    not secrets).
    """
    return (module_path, attr_name)


# Lazy imports for optional components
_LAZY_IMPORTS = {
    "WebSocketMCPClient": _t("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPClient"),
    "SessionManager": _t("praisonaiagents.mcp.mcp_session", "SessionManager"),
    "SecurityConfig": _t("praisonaiagents.mcp.mcp_security", "SecurityConfig"),
    "BaseTransport": _t("praisonaiagents.mcp.mcp_transport", "BaseTransport"),
    "TransportConfig": _t("praisonaiagents.mcp.mcp_transport", "TransportConfig"),
    "ToolsMCPServer": _t("praisonaiagents.mcp.mcp_server", "ToolsMCPServer"),
    "launch_tools_mcp_server": _t("praisonaiagents.mcp.mcp_server", "launch_tools_mcp_server"),
    "function_to_mcp_schema": _t("praisonaiagents.mcp.mcp_utils", "function_to_mcp_schema"),
    "get_tool_metadata": _t("praisonaiagents.mcp.mcp_utils", "get_tool_metadata"),
    "python_type_to_json_schema": _t("praisonaiagents.mcp.mcp_utils", "python_type_to_json_schema"),
    "fix_array_schemas": _t("praisonaiagents.mcp.mcp_schema_utils", "fix_array_schemas"),
    "ThreadLocalEventLoop": _t("praisonaiagents.mcp.mcp_schema_utils", "ThreadLocalEventLoop"),
    "get_thread_local_event_loop": _t("praisonaiagents.mcp.mcp_schema_utils", "get_thread_local_event_loop"),
    # Auth storage (lazy loaded) — import targets, not credentials.
    "MCPAuthStorage": _t("praisonaiagents.mcp.mcp_auth_storage", "MCPAuthStorage"),
    "get_default_auth_filepath": _t("praisonaiagents.mcp.mcp_auth_storage", "get_default_auth_filepath"),
    # OAuth callback utilities (lazy loaded) — import targets, not credentials.
    "OAuthCallbackHandler": _t("praisonaiagents.mcp.mcp_oauth_callback", "OAuthCallbackHandler"),
    "generate_state": _t("praisonaiagents.mcp.mcp_oauth_callback", "generate_state"),
    "generate_code_verifier": _t("praisonaiagents.mcp.mcp_oauth_callback", "generate_code_verifier"),
    "generate_code_challenge": _t("praisonaiagents.mcp.mcp_oauth_callback", "generate_code_challenge"),
    "get_redirect_url": _t("praisonaiagents.mcp.mcp_oauth_callback", "get_redirect_url"),
    "OAUTH_CALLBACK_PORT": _t("praisonaiagents.mcp.mcp_oauth_callback", "OAUTH_CALLBACK_PORT"),
    "OAUTH_CALLBACK_PATH": _t("praisonaiagents.mcp.mcp_oauth_callback", "OAUTH_CALLBACK_PATH"),
    # Zero-config OAuth: discovery, dynamic registration, orchestration.
    "discover_oauth_metadata": _t("praisonaiagents.mcp.oauth_discovery", "discover_oauth_metadata"),
    "parse_www_authenticate": _t("praisonaiagents.mcp.oauth_discovery", "parse_www_authenticate"),
    "register_client": _t("praisonaiagents.mcp.oauth_registration", "register_client"),
    "MCPOAuthProvider": _t("praisonaiagents.mcp.oauth_provider", "MCPOAuthProvider"),
    "InteractiveAuthRequired": _t("praisonaiagents.mcp.oauth_provider", "InteractiveAuthRequired"),
    # Protocols (lazy loaded)
    "MCPClientProtocol": _t("praisonaiagents.mcp.protocols", "MCPClientProtocol"),
    # Loader (lazy loaded)
    "load_mcp_tools": _t("praisonaiagents.mcp.loader", "load_mcp_tools"),
    # Resource/prompt normalisation helpers (lazy loaded)
    "normalize_resource_result": _t("praisonaiagents.mcp.resources", "normalize_resource_result"),
    "normalize_prompt_result": _t("praisonaiagents.mcp.resources", "normalize_prompt_result"),
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
    # Zero-config OAuth (lazy loaded)
    "discover_oauth_metadata",
    "parse_www_authenticate",
    "register_client",
    "MCPOAuthProvider",
    "InteractiveAuthRequired",
]
