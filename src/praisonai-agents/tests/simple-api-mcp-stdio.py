"""
Simple API example using MCP stdio (no separate server required).

This example creates a temporary MCP server script and uses it with stdio transport,
which is simpler than SSE as it doesn't require running a separate server process.
"""

import os
import sys
from praisonaiagents import Agent, MCP

# Create a simple MCP server script
mcp_server_code = '''
from mcp.server.fastmcp import FastMCP

# Create MCP server instance
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
        "Sydney": "Partly cloudy, 20°C",
        "Berlin": "Overcast, 16°C",
        "Mumbai": "Hot and humid, 32°C",
        "Toronto": "Snowy, -5°C"
    }
    
    return weather_data.get(city, f"Weather information not available for {city}. Try cities like Paris, London, New York, Tokyo, or Sydney.")

# Run the MCP server
if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run())
'''

# Write the MCP server script to a temporary file
script_path = "temp_weather_mcp_server.py"
with open(script_path, "w") as f:
    f.write(mcp_server_code)

try:
    # Get the Python executable path
    python_exe = sys.executable
    
    # Create agent with MCP stdio connection
    weather_agent = Agent(
        instructions="""You are a helpful weather agent that can provide weather information for cities around the world.
        When asked about weather, use the get_weather tool to fetch the information.""",
        llm="openai/gpt-4o-mini",
        tools=MCP(f"{python_exe} {script_path}")
    )
    
    # Launch the API server
    print("Weather Agent API started at http://localhost:3030/weather")
    print("\nExample requests:")
    print("  curl -X POST http://localhost:3030/weather -H 'Content-Type: application/json' -d '{\"message\": \"What is the weather in Paris?\"}'")
    print("  curl -X POST http://localhost:3030/weather -H 'Content-Type: application/json' -d '{\"message\": \"Tell me about the weather in Tokyo and London\"}'")
    print("\nPress Ctrl+C to stop the server")
    
    weather_agent.launch(path="/weather", port=3030)
    
finally:
    # Clean up the temporary script file
    if os.path.exists(script_path):
        os.remove(script_path)
        print(f"\nCleaned up temporary file: {script_path}")