"""MCP server hosting for PraisonAI — expose agents and tools to MCP clients.

Example:
    praisonai-mcp serve --transport stdio

    from praisonai_mcp.mcp_server import MCPServer
    server = MCPServer()
    server.run(transport="stdio")
"""

from __future__ import annotations

from praisonai_mcp._version import __version__


def __getattr__(name: str):
    if name == "MCPServer":
        from praisonai_mcp.mcp_server.server import MCPServer
        return MCPServer
    if name == "handle_mcp_command":
        from praisonai_mcp.mcp_server.cli import handle_mcp_command
        return handle_mcp_command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["__version__", "MCPServer", "handle_mcp_command"]
