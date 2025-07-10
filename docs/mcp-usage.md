# MCP (Model Context Protocol) Usage Guide

MCP allows you to connect your PraisonAI agents to external tools and services. There are two main transport methods: **stdio** and **SSE**.

## Quick Start

### Method 1: Stdio Transport (Recommended for beginners)

This is the simplest method as it doesn't require running a separate server:

```python
from praisonaiagents import Agent, MCP
import sys

# Use a Python script as MCP server
agent = Agent(
    instructions="You are a helpful assistant",
    llm="openai/gpt-4o-mini",
    tools=MCP(f"{sys.executable} path/to/mcp_server.py")
)

agent.start("Your query here")
```

### Method 2: SSE Transport

SSE requires running a separate server first:

```python
# Terminal 1: Start the MCP SSE server
# python mcp-sse-server.py

# Terminal 2: Connect to the server
from praisonaiagents import Agent, MCP

agent = Agent(
    instructions="You are a helpful assistant",
    llm="openai/gpt-4o-mini",
    tools=MCP("http://localhost:8080/sse")
)
```

## Common Issues

### ConnectionError: All connection attempts failed

This error occurs when trying to use SSE transport without a running server.

**Solution**: 
1. Start the MCP SSE server first: `python mcp-sse-server.py`
2. Then run your agent code
3. Or switch to stdio transport which doesn't require a separate server

### Creating an MCP Server

Here's a minimal MCP server example:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-tools")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description"""
    return f"Result for {param}"

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run())
```

## Examples

### Weather Service Example (Stdio)

```python
import os
import sys
from praisonaiagents import Agent, MCP

# Create MCP server script
server_code = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

@mcp.tool()
async def get_weather(city: str) -> str:
    """Get weather for a city"""
    return f"Weather in {city}: Sunny, 22°C"

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run())
'''

# Save and use the server
with open("weather_server.py", "w") as f:
    f.write(server_code)

agent = Agent(
    instructions="You are a weather assistant",
    llm="openai/gpt-4o-mini",
    tools=MCP(f"{sys.executable} weather_server.py")
)

result = agent.start("What's the weather in Paris?")
print(result)

# Cleanup
os.remove("weather_server.py")
```

### API Server with MCP

```python
from praisonaiagents import Agent, MCP

agent = Agent(
    instructions="You are an API assistant",
    llm="openai/gpt-4o-mini",
    tools=MCP(f"{sys.executable} mcp_server.py")
)

# Launch as API
agent.launch(path="/assistant", port=8000)
```

## Best Practices

1. **Use stdio for development** - It's simpler and doesn't require managing separate processes
2. **Use SSE for production** - Better for scalability and distributed systems
3. **Handle connection errors** - Always wrap SSE connections in try-except blocks
4. **Provide clear tool descriptions** - This helps the LLM understand when to use each tool
5. **Test tools independently** - Verify your MCP server works before integrating with agents

## Transport Comparison

| Feature | Stdio | SSE |
|---------|-------|-----|
| Setup complexity | Simple | Requires separate server |
| Performance | Good for single instance | Better for multiple clients |
| Debugging | Easier | More complex |
| Use case | Development, single agents | Production, multiple agents |

## Debugging Tips

1. **Enable debug logging**:
   ```python
   tools=MCP("...", debug=True)
   ```

2. **Test MCP server separately**:
   ```bash
   python your_mcp_server.py
   ```

3. **Check server is running** (for SSE):
   ```bash
   curl http://localhost:8080/sse
   ```

4. **Verify tool discovery**:
   ```python
   # The MCP client will automatically discover and list available tools
   ```