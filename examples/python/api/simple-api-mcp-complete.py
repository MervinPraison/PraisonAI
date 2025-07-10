"""
Complete example showing how to use MCP with SSE in PraisonAI Agents.

This example demonstrates:
1. Setting up an MCP SSE server
2. Creating an agent that connects to the server
3. Proper error handling

There are two ways to run this:

Option 1 - Run server and client separately:
    Terminal 1: python simple-api-mcp-complete.py --server
    Terminal 2: python simple-api-mcp-complete.py --client

Option 2 - Use stdio-based MCP (no separate server needed):
    python simple-api-mcp-complete.py --stdio
"""

import argparse
import os
import sys
from typing import Any

# For SSE server
try:
    from mcp.server.fastmcp import FastMCP
    from starlette.applications import Starlette
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.routing import Mount, Route
    from mcp.server import Server
    import uvicorn
    MCP_SERVER_AVAILABLE = True
except ImportError:
    MCP_SERVER_AVAILABLE = False

# For client
from praisonaiagents import Agent, MCP


def create_mcp_server():
    """Create an MCP SSE server with weather tools."""
    if not MCP_SERVER_AVAILABLE:
        print("Error: MCP server dependencies not installed.")
        print("Please install with: pip install 'praisonaiagents[mcp]'")
        sys.exit(1)
    
    # Initialize FastMCP server
    mcp = FastMCP("weather-service")

    @mcp.tool()
    async def get_weather(city: str) -> str:
        """Get weather information for a given city.
        
        Args:
            city: Name of the city
        """
        # Mock weather data
        weather_data = {
            "Paris": "Sunny, 22°C",
            "London": "Rainy, 15°C", 
            "New York": "Cloudy, 18°C",
            "Tokyo": "Clear, 25°C",
            "Sydney": "Partly cloudy, 20°C"
        }
        
        return weather_data.get(city, f"Weather data not available for {city}")

    def create_starlette_app(mcp_server: Server) -> Starlette:
        """Create a Starlette application for SSE."""
        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,
            ) as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options(),
                )

        return Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

    # Get the MCP server instance
    mcp_server = mcp._mcp_server
    
    # Create Starlette app
    app = create_starlette_app(mcp_server)
    
    # Run the server
    print("Starting MCP SSE server on http://localhost:8080/sse")
    print("Available tools: get_weather")
    print("\nIn another terminal, run:")
    print("python simple-api-mcp-complete.py --client")
    
    uvicorn.run(app, host="localhost", port=8080)


def create_sse_client():
    """Create an agent that uses MCP SSE."""
    print("Creating agent with MCP SSE connection...")
    
    try:
        # Create agent with MCP SSE connection
        weather_agent = Agent(
            instructions="You are a weather agent that can provide weather information for cities.",
            llm="openai/gpt-4o-mini",
            tools=MCP("http://localhost:8080/sse")
        )
        
        # Launch the agent API
        print("\nAgent API started at http://localhost:3030/weather")
        print("Try: curl -X POST http://localhost:3030/weather -H 'Content-Type: application/json' -d '{\"message\": \"What is the weather in Paris?\"}'")
        
        weather_agent.launch(path="/weather", port=3030)
        
    except ConnectionError as e:
        print(f"\nError: {e}")
        print("\nMake sure the MCP server is running first!")
        sys.exit(1)


def create_stdio_example():
    """Create a working example using stdio-based MCP."""
    # First, let's create a simple MCP server script
    server_script = """
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather-service")

@mcp.tool()
async def get_weather(city: str) -> str:
    '''Get weather information for a city.'''
    weather_data = {
        "Paris": "Sunny, 22°C",
        "London": "Rainy, 15°C",
        "New York": "Cloudy, 18°C"
    }
    return weather_data.get(city, f"No data for {city}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run())
"""
    
    # Write the server script
    script_path = "weather_mcp_server.py"
    with open(script_path, "w") as f:
        f.write(server_script)
    
    print(f"Created MCP server script: {script_path}")
    
    # Get Python executable path
    python_path = sys.executable
    
    # Create agent with stdio MCP
    print(f"\nCreating agent with stdio MCP connection...")
    print(f"Using Python: {python_path}")
    
    weather_agent = Agent(
        instructions="You are a weather agent that can provide weather information for cities.",
        llm="openai/gpt-4o-mini",
        tools=MCP(f"{python_path} {script_path}")
    )
    
    # Test the agent
    print("\nTesting agent...")
    result = weather_agent.start("What's the weather in Paris?")
    print(f"Agent response: {result}")
    
    # Clean up
    os.remove(script_path)
    print(f"\nCleaned up temporary file: {script_path}")


def main():
    parser = argparse.ArgumentParser(description="MCP SSE Example")
    parser.add_argument("--server", action="store_true", help="Run as MCP SSE server")
    parser.add_argument("--client", action="store_true", help="Run as client with SSE")
    parser.add_argument("--stdio", action="store_true", help="Run stdio example (no server needed)")
    
    args = parser.parse_args()
    
    if args.server:
        create_mcp_server()
    elif args.client:
        create_sse_client()
    elif args.stdio:
        create_stdio_example()
    else:
        print("Please specify --server, --client, or --stdio")
        print("\nExamples:")
        print("  python simple-api-mcp-complete.py --stdio   # Easiest - no separate server needed")
        print("  python simple-api-mcp-complete.py --server  # Run SSE server")
        print("  python simple-api-mcp-complete.py --client  # Run SSE client (requires server)")


if __name__ == "__main__":
    main()