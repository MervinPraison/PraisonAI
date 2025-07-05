"""
Example demonstrating HTTP-Streaming support for MCP in PraisonAI Agents.

This example shows how to use the new HTTP-Streaming transport with backward compatibility.
"""

from praisonaiagents import Agent
from praisonaiagents.mcp import MCP

# Example 1: Auto-detection (backward compatible)
print("Example 1: Auto-detection of transport")
print("======================================")

# URLs ending with /sse will use SSE transport
agent_sse = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/sse")  # Auto-detects SSE
)

# Other HTTP URLs will use HTTP-Streaming transport
agent_http = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/stream")  # Auto-detects HTTP-Streaming
)

# Example 2: Explicit transport selection
print("\nExample 2: Explicit transport selection")
print("========================================")

# Force SSE transport
agent_force_sse = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/api", transport="sse")
)

# Force HTTP-Streaming transport
agent_force_http = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/api", transport="http-streaming")
)

# Example 3: Stdio transport (backward compatible)
print("\nExample 3: Stdio transport (unchanged)")
print("======================================")

agent_stdio = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("/path/to/python /path/to/server.py")  # Stdio transport
)

# Example 4: Using with debug mode
print("\nExample 4: Debug mode")
print("=====================")

agent_debug = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/stream", transport="http-streaming", debug=True)
)

# Example 5: Complete backward compatibility
print("\nExample 5: Complete backward compatibility")
print("==========================================")

# All existing code continues to work without any changes
# This is exactly how it worked before
agent_legacy = Agent(
    instructions="You are a weather assistant",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8080/sse")
)

# Run the agent (if server is available)
try:
    response = agent_legacy.start("What's the weather like?")
    print(f"Response: {response}")
except Exception as e:
    print(f"Note: Server not running. This is just an example.")
    print(f"Error: {e}")

print("\nAll examples demonstrate backward compatibility!")
print("Existing code requires ZERO changes.")