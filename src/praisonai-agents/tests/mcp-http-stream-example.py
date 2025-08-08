#!/usr/bin/env python
"""
Example of using MCP with HTTP Stream transport.
This demonstrates how to connect to an MCP server using the new HTTP Stream transport.
"""

from praisonaiagents import Agent
from praisonaiagents.mcp import MCP

# Example 1: Basic HTTP Stream connection (defaults to /mcp endpoint)
print("Example 1: Basic HTTP Stream connection")
try:
    # This will use HTTP Stream transport automatically
    tools = MCP("http://localhost:8080", debug=True)
    print(f"Connected! Found {len(list(tools))} tools")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
except Exception as e:
    print(f"Connection failed: {e}")

print("\n" + "="*50 + "\n")

# Example 2: HTTP Stream with custom endpoint
print("Example 2: HTTP Stream with custom endpoint")
try:
    # This will use HTTP Stream transport with custom endpoint
    tools = MCP("http://localhost:8080/custom-mcp", debug=True)
    print(f"Connected! Found {len(list(tools))} tools")
except Exception as e:
    print(f"Connection failed: {e}")

print("\n" + "="*50 + "\n")

# Example 3: HTTP Stream with stream response mode
print("Example 3: HTTP Stream with stream response mode")
try:
    # This will use HTTP Stream transport with streaming responses
    tools = MCP("http://localhost:8080", responseMode="stream", debug=True)
    print(f"Connected! Found {len(list(tools))} tools")
except Exception as e:
    print(f"Connection failed: {e}")

print("\n" + "="*50 + "\n")

# Example 4: Backward compatibility - SSE transport
print("Example 4: Backward compatibility - SSE transport")
try:
    # URLs ending with /sse will still use SSE transport
    tools = MCP("http://localhost:8080/sse", debug=True)
    print(f"Connected using SSE! Found {len(list(tools))} tools")
except Exception as e:
    print(f"Connection failed: {e}")

print("\n" + "="*50 + "\n")

# Example 5: Using with an agent
print("Example 5: Using HTTP Stream tools with an agent")
try:
    agent = Agent(
        name="Weather Assistant",
        instructions="You are a helpful weather assistant.",
        tools=MCP("http://localhost:8080"),  # HTTP Stream transport
        llm="gpt-5-nano"
    )
    print("Agent created successfully with HTTP Stream tools!")
    
    # Example usage (commented out to avoid actual API calls)
    # result = agent.execute("What's the weather in Paris?")
    # print(f"Result: {result}")
except Exception as e:
    print(f"Agent creation failed: {e}")

print("\n" + "="*50 + "\n")

# Example 6: HTTP Stream with custom headers and CORS
print("Example 6: HTTP Stream with custom configuration")
try:
    tools = MCP(
        "http://localhost:8080",
        headers={"X-API-Key": "my-api-key"},
        cors={"allowOrigin": "*"},
        debug=True
    )
    print(f"Connected with custom config! Found {len(list(tools))} tools")
except Exception as e:
    print(f"Connection failed: {e}")

print("\nNote: These examples require an HTTP Stream MCP server running on localhost:8080")