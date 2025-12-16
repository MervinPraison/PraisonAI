"""
MCP Resumability Example

Demonstrates SSE stream resumability for MCP transports.
Resumability allows recovering from disconnections without losing messages.

Features:
- Event ID tracking per stream
- Last-Event-ID header on reconnection
- Retry delay handling from server
- Message replay on reconnection

Protocol: MCP 2025-11-25
"""

from praisonaiagents import Agent, MCP

# Agent with resumability support (automatic)
agent = Agent(
    name="Resumable Assistant",
    instructions="You are a helpful assistant with resumable connections.",
    tools=MCP("https://api.example.com/mcp")
)

# Resumability is automatic - the MCP client:
# 1. Tracks event IDs from SSE streams (id: field)
# 2. Stores last event ID per stream
# 3. Includes Last-Event-ID header on reconnection
# 4. Respects retry delay from server (retry: field)

if __name__ == "__main__":
    print("MCP Resumability Example")
    print("=" * 40)
    print()
    print("SSE Event Format:")
    print("  id: event-123")
    print("  retry: 3000")
    print("  data: {\"jsonrpc\": \"2.0\", ...}")
    print()
    print("Resumability Flow:")
    print("1. Client receives SSE events with id: field")
    print("2. Client stores last event ID")
    print("3. On disconnection, client reconnects with Last-Event-ID header")
    print("4. Server replays messages after that event ID")
    print("5. Client respects retry: field for reconnection delay")
    print()
    print("This prevents message loss during network interruptions.")
