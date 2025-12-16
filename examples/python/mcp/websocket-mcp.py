"""
MCP WebSocket Transport Example

Demonstrates connecting to MCP servers via WebSocket (ws:// or wss://).
WebSocket transport provides bidirectional real-time communication,
ideal for cloud deployments and long-lived connections.

Features:
- Auto-detection of ws:// and wss:// URLs
- Authentication token support
- Auto-reconnect with exponential backoff
- Ping/pong keepalive

Protocol: SEP-1288 (WebSocket Transport)
"""

from praisonaiagents import Agent, MCP

# Basic WebSocket connection
agent = Agent(
    name="WebSocket Assistant",
    instructions="You are a helpful assistant connected via WebSocket.",
    tools=MCP("ws://localhost:8080/mcp")
)

# Secure WebSocket with authentication
agent_secure = Agent(
    name="Secure WebSocket Assistant",
    instructions="You are a helpful assistant with secure WebSocket connection.",
    tools=MCP(
        "wss://api.example.com/mcp",
        auth_token="Bearer your-secret-token",
        timeout=60
    )
)

# WebSocket with custom options
agent_custom = Agent(
    name="Custom WebSocket Assistant",
    tools=MCP(
        "wss://api.example.com/mcp",
        auth_token="your-token",
        timeout=120,
        debug=True
    )
)

if __name__ == "__main__":
    # Note: Requires a running WebSocket MCP server
    # Example server: https://github.com/modelcontextprotocol/servers
    
    print("WebSocket MCP Transport Example")
    print("=" * 40)
    print("This example requires a WebSocket MCP server running.")
    print("URL patterns: ws://host:port/path or wss://host:port/path")
