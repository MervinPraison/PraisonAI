"""
MCP Session Management Example

Demonstrates session management features for MCP transports.
Sessions allow stateful interactions with MCP servers.

Features:
- Automatic session ID handling
- Session expiration detection (HTTP 404)
- Session termination via HTTP DELETE
- Protocol version negotiation

Protocol: MCP 2025-11-25
"""

from praisonaiagents import Agent, MCP

# Basic agent with automatic session management
agent = Agent(
    name="Session Assistant",
    instructions="You are a helpful assistant with session support.",
    tools=MCP("https://api.example.com/mcp")
)

# Session management is automatic - the MCP client:
# 1. Receives Mcp-Session-Id from server during initialization
# 2. Includes session ID in all subsequent requests
# 3. Handles HTTP 404 (session expired) by reinitializing
# 4. Can terminate session explicitly when done

if __name__ == "__main__":
    print("MCP Session Management Example")
    print("=" * 40)
    print()
    print("Session Lifecycle:")
    print("1. Client sends InitializeRequest")
    print("2. Server returns InitializeResult with Mcp-Session-Id header")
    print("3. Client includes Mcp-Session-Id in all subsequent requests")
    print("4. If HTTP 404 received, client reinitializes session")
    print("5. Client can send HTTP DELETE to terminate session")
    print()
    print("Headers used:")
    print("- Mcp-Session-Id: Session identifier")
    print("- Mcp-Protocol-Version: Protocol version (e.g., 2025-03-26)")
