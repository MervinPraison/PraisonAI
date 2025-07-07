"""
Example demonstrating MCP with HTTP-Streaming transport.

This example shows:
1. Auto-detection of transport based on URL
2. Explicit transport selection
3. Backward compatibility with existing code
"""

from praisonaiagents import Agent
from praisonaiagents.mcp import MCP

# Example 1: Auto-detection - SSE endpoint (backward compatible)
print("Example 1: Auto-detection with SSE endpoint")
try:
    agent_sse_auto = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP("http://localhost:8080/sse")  # Auto-detects SSE transport
    )
    print("✓ SSE transport detected automatically")
except Exception as e:
    print(f"Note: {e}")

# Example 2: Auto-detection - HTTP endpoint
print("\nExample 2: Auto-detection with HTTP endpoint")
try:
    agent_http_auto = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP("http://localhost:8080/api")  # Auto-detects HTTP-streaming transport
    )
    print("✓ HTTP-streaming transport detected automatically")
except Exception as e:
    print(f"Note: {e}")

# Example 3: Explicit SSE transport
print("\nExample 3: Explicit SSE transport selection")
try:
    agent_sse_explicit = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP("http://localhost:8080/api", transport="sse")  # Force SSE
    )
    print("✓ SSE transport explicitly selected")
except Exception as e:
    print(f"Note: {e}")

# Example 4: Explicit HTTP-streaming transport
print("\nExample 4: Explicit HTTP-streaming transport selection")
try:
    agent_http_explicit = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP("http://localhost:8080/sse", transport="http-streaming")  # Force HTTP-streaming
    )
    print("✓ HTTP-streaming transport explicitly selected")
except Exception as e:
    print(f"Note: {e}")

# Example 5: HTTP-streaming with custom headers
print("\nExample 5: HTTP-streaming with custom headers")
try:
    agent_http_headers = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP(
            "http://localhost:8080/api",
            transport="http-streaming",
            headers={"Authorization": "Bearer your-token-here"}
        )
    )
    print("✓ HTTP-streaming with custom headers configured")
except Exception as e:
    print(f"Note: {e}")

# Example 6: Existing stdio usage - completely unchanged
print("\nExample 6: Existing stdio usage (backward compatible)")
try:
    agent_stdio = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP(
            command="/path/to/python",
            args=["/path/to/mcp_server.py"]
        )
    )
    print("✓ Stdio transport works as before")
except Exception as e:
    print(f"Note: {e}")

# Example 7: NPX usage - completely unchanged
print("\nExample 7: NPX usage (backward compatible)")
try:
    agent_npx = Agent(
        instructions="You are a helpful assistant that can use MCP tools.",
        llm="gpt-4o-mini",
        tools=MCP("npx @modelcontextprotocol/server-brave-search")
    )
    print("✓ NPX transport works as before")
except Exception as e:
    print(f"Note: {e}")

print("\n" + "="*50)
print("Summary: HTTP-Streaming support added with full backward compatibility!")
print("- Auto-detection: URLs ending with /sse use SSE, others use HTTP-streaming")
print("- Explicit control: Use transport='sse' or transport='http-streaming'")
print("- All existing code continues to work without modification")
print("="*50)