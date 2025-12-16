"""
MCP Backward Compatibility Example

Demonstrates backward compatibility with older MCP servers
using the deprecated HTTP+SSE transport (protocol version 2024-11-05).

Features:
- Legacy SSE endpoint detection (/sse suffix)
- Automatic transport negotiation
- Protocol version support (2024-11-05 to 2025-11-25)

Protocol: MCP 2025-11-25 with 2024-11-05 compatibility
"""

# Example code (requires running MCP servers):
#
# from praisonaiagents import Agent, MCP
#
# # Legacy SSE server (auto-detected via /sse suffix)
# agent_legacy = Agent(
#     name="Legacy SSE Assistant",
#     tools=MCP("http://localhost:8080/sse")
# )
#
# # Modern Streamable HTTP server
# agent_modern = Agent(
#     name="Modern HTTP Assistant",
#     tools=MCP("http://localhost:8080/mcp")
# )

if __name__ == "__main__":
    from praisonaiagents.mcp.mcp_transport import get_transport_type
    from praisonaiagents.mcp.mcp_compat import (
        detect_transport_support,
        is_legacy_sse_url,
        TransportNegotiator
    )
    from praisonaiagents.mcp.mcp_session import VALID_PROTOCOL_VERSIONS
    
    print("MCP Backward Compatibility Example")
    print("=" * 50)
    
    # URL detection
    print("\n1. URL-based Transport Detection:")
    urls = [
        "http://localhost:8080/sse",
        "https://api.example.com/sse",
        "http://localhost:8080/mcp",
        "https://api.example.com/mcp",
    ]
    for url in urls:
        transport = get_transport_type(url)
        legacy = is_legacy_sse_url(url)
        print(f"   {url}")
        print(f"      Transport: {transport}, Legacy: {legacy}")
    
    # Transport negotiation
    print("\n2. Transport Negotiation (HTTP response based):")
    responses = [
        (200, "application/json", "Streamable HTTP"),
        (200, "text/event-stream", "SSE stream"),
        (400, None, "Fallback to SSE"),
        (404, None, "Fallback to SSE"),
        (405, None, "Fallback to SSE"),
    ]
    for status, content_type, desc in responses:
        detected = detect_transport_support(status, content_type)
        print(f"   HTTP {status} ({desc}): {detected}")
    
    # Protocol versions
    print("\n3. Supported Protocol Versions:")
    for version in sorted(VALID_PROTOCOL_VERSIONS):
        print(f"   - {version}")
    
    # Negotiator
    print("\n4. Transport Negotiator:")
    negotiator = TransportNegotiator("https://api.example.com/mcp")
    print(f"   Base URL: {negotiator.base_url}")
    print(f"   Try Streamable first: {negotiator.should_try_streamable_first()}")
    
    negotiator_sse = TransportNegotiator("https://api.example.com/sse")
    print(f"   SSE URL: {negotiator_sse.base_url}")
    print(f"   Try Streamable first: {negotiator_sse.should_try_streamable_first()}")
