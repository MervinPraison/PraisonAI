"""
MCP Streamable HTTP Transport Example

Demonstrates connecting to MCP servers via Streamable HTTP transport.
This is the current standard transport (Protocol Revision 2025-11-25).

Features:
- Single MCP endpoint for all communication
- Session management via Mcp-Session-Id header
- Protocol versioning via Mcp-Protocol-Version header
- SSE streaming with resumability
- Session termination via HTTP DELETE

Protocol: MCP 2025-11-25
"""

from praisonaiagents import Agent, MCP

# Basic Streamable HTTP connection
agent = Agent(
    name="HTTP Stream Assistant",
    instructions="You are a helpful assistant connected via Streamable HTTP.",
    tools=MCP("https://api.example.com/mcp")
)

# With authentication headers
agent_auth = Agent(
    name="Authenticated Assistant",
    instructions="You are a helpful assistant with authenticated connection.",
    tools=MCP(
        "https://api.example.com/mcp",
        headers={"Authorization": "Bearer your-token"}
    )
)

# With timeout and debug
agent_debug = Agent(
    name="Debug Assistant",
    tools=MCP(
        "https://api.example.com/mcp",
        timeout=120,
        debug=True
    )
)

if __name__ == "__main__":
    print("Streamable HTTP MCP Transport Example")
    print("=" * 40)
    print("This example requires a Streamable HTTP MCP server running.")
    print("URL pattern: https://host:port/mcp")
    print()
    print("Features enabled:")
    print("- Mcp-Protocol-Version header (default: 2025-03-26)")
    print("- Mcp-Session-Id header (automatic)")
    print("- SSE streaming support")
    print("- Resumability via Last-Event-ID")
