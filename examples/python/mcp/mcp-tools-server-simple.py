"""Simple MCP Tools Server Example

Minimal example of exposing Python functions as MCP tools.

Usage:
    python mcp-tools-server-simple.py
"""

from praisonaiagents.mcp import ToolsMCPServer


def search(query: str) -> dict:
    """Search for information."""
    return {"query": query, "results": [f"Result for {query}"]}


def add(a: int, b: int) -> dict:
    """Add two numbers."""
    return {"result": a + b}


if __name__ == "__main__":
    server = ToolsMCPServer(name="simple-tools")
    server.register_tools([search, add])
    server.run()
