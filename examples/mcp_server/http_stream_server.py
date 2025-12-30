#!/usr/bin/env python3
"""
HTTP Stream MCP Server Example

Run PraisonAI as an MCP server using HTTP Stream transport.
This transport is useful for web-based integrations.

Usage:
    python http_stream_server.py

Or via CLI:
    praisonai mcp serve --transport http-stream --port 8080
"""


def main():
    """Run MCP server with HTTP Stream transport."""
    from praisonai.mcp_server.server import MCPServer
    from praisonai.mcp_server.adapters import register_all
    
    # Register all tools, resources, and prompts
    register_all()
    
    # Create server
    server = MCPServer(
        name="praisonai",
        version="1.0.0",
        instructions="PraisonAI MCP Server - AI agent capabilities via MCP protocol.",
    )
    
    # Run with HTTP Stream transport
    server.run(
        transport="http-stream",
        host="127.0.0.1",
        port=8080,
        endpoint="/mcp",
    )


if __name__ == "__main__":
    print("Starting PraisonAI MCP Server on http://127.0.0.1:8080/mcp")
    print("Protocol Version: 2025-11-25")
    print("Press Ctrl+C to stop")
    main()
