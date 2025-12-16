"""
Model Context Protocol (MCP) integration for PraisonAI Agents.

This package provides classes and utilities for:
- Connecting to MCP servers (as client) using different transports (stdio, SSE, etc.)
- Exposing Python functions as MCP servers for external clients

Client Usage:
    from praisonaiagents.mcp import MCP
    
    agent = Agent(
        tools=MCP("npx -y @modelcontextprotocol/server-weather")
    )

Server Usage:
    from praisonaiagents.mcp import ToolsMCPServer
    
    def my_tool(query: str) -> str:
        '''Search for information.'''
        return f"Results for {query}"
    
    server = ToolsMCPServer(name="my-tools")
    server.register_tool(my_tool)
    server.run()  # Starts MCP server
"""
from .mcp import MCP
from .mcp_server import ToolsMCPServer, launch_tools_mcp_server
from .mcp_utils import function_to_mcp_schema, get_tool_metadata, python_type_to_json_schema

__all__ = [
    # Client
    "MCP",
    # Server
    "ToolsMCPServer",
    "launch_tools_mcp_server",
    # Utilities
    "function_to_mcp_schema",
    "get_tool_metadata",
    "python_type_to_json_schema",
]
