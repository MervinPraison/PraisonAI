"""
PraisonAI MCP Server Module

Exposes PraisonAI capabilities as an MCP server that any MCP client can connect to.

Supports:
- STDIO transport (default, for Claude Desktop, Cursor, etc.)
- HTTP Stream transport (MCP 2025-03-26 spec)

Usage:
    # STDIO mode (for Claude Desktop config)
    praisonai mcp serve --transport stdio
    
    # HTTP Stream mode
    praisonai mcp serve --transport http-stream --port 8080
    
    # Programmatic usage
    from praisonai.mcp_server import MCPServer
    
    server = MCPServer()
    server.run(transport="stdio")
"""

__all__ = [
    "MCPServer",
    "MCPToolRegistry",
    "MCPResourceRegistry",
    "MCPPromptRegistry",
    "register_tool",
    "register_resource",
    "register_prompt",
]


def __getattr__(name):
    """Lazy load server components."""
    if name == "MCPServer":
        from .server import MCPServer
        return MCPServer
    elif name == "MCPToolRegistry":
        from .registry import MCPToolRegistry
        return MCPToolRegistry
    elif name == "MCPResourceRegistry":
        from .registry import MCPResourceRegistry
        return MCPResourceRegistry
    elif name == "MCPPromptRegistry":
        from .registry import MCPPromptRegistry
        return MCPPromptRegistry
    elif name == "register_tool":
        from .registry import register_tool
        return register_tool
    elif name == "register_resource":
        from .registry import register_resource
        return register_resource
    elif name == "register_prompt":
        from .registry import register_prompt
        return register_prompt
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
