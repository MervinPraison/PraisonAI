"""
MCP Transports Overview Example

Demonstrates all MCP transport types and auto-detection.
The MCP class automatically selects the appropriate transport
based on the URL pattern.

Transport Types:
- stdio: Command strings (local subprocess)
- Streamable HTTP: http:// or https:// URLs
- WebSocket: ws:// or wss:// URLs
- SSE (Legacy): URLs ending in /sse

Protocol: MCP 2025-11-25
"""

# Example code (requires running MCP servers):
#
# from praisonaiagents import Agent, MCP
#
# # 1. stdio Transport - Local subprocess
# agent_stdio = Agent(
#     name="Stdio Assistant",
#     tools=MCP("npx @modelcontextprotocol/server-memory")
# )
#
# # 2. Streamable HTTP Transport
# agent_http = Agent(
#     name="HTTP Assistant",
#     tools=MCP("https://api.example.com/mcp")
# )
#
# # 3. WebSocket Transport
# agent_ws = Agent(
#     name="WebSocket Assistant",
#     tools=MCP("wss://api.example.com/mcp")
# )
#
# # 4. SSE Transport (Legacy)
# agent_sse = Agent(
#     name="SSE Assistant",
#     tools=MCP("http://localhost:8080/sse")
# )

if __name__ == "__main__":
    from praisonaiagents.mcp.mcp_transport import get_transport_type
    
    print("MCP Transports Overview")
    print("=" * 50)
    print()
    print("Transport Auto-Detection:")
    print("-" * 50)
    
    examples = [
        ("npx @mcp/server-memory", "stdio"),
        ("python3 server.py", "stdio"),
        ("https://api.example.com/mcp", "http_stream"),
        ("http://localhost:8080/mcp", "http_stream"),
        ("ws://localhost:8080/mcp", "websocket"),
        ("wss://api.example.com/mcp", "websocket"),
        ("http://localhost:8080/sse", "sse"),
        ("https://api.example.com/sse", "sse"),
    ]
    
    for url, expected in examples:
        detected = get_transport_type(url)
        status = "✓" if detected == expected else "✗"
        print(f"  {status} '{url}'")
        print(f"      → {detected}")
    
    print()
    print("Transport Features:")
    print("-" * 50)
    print("  stdio:")
    print("    - Local subprocess communication")
    print("    - Newline-delimited JSON-RPC")
    print("    - Environment variable support")
    print()
    print("  Streamable HTTP:")
    print("    - Session management (Mcp-Session-Id)")
    print("    - Protocol versioning (Mcp-Protocol-Version)")
    print("    - SSE streaming with resumability")
    print()
    print("  WebSocket:")
    print("    - Bidirectional real-time")
    print("    - Auto-reconnect with exponential backoff")
    print("    - Authentication token support")
    print()
    print("  SSE (Legacy):")
    print("    - Backward compatibility")
    print("    - Protocol version 2024-11-05")
