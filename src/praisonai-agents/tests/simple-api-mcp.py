"""
Simple API example using MCP with PraisonAI Agents.

IMPORTANT: This example requires an MCP SSE server to be running first!

To run this example:
1. First start the MCP server: python mcp-sse-direct-server.py
2. Then run this script: python simple-api-mcp.py

For a simpler example that doesn't require a separate server, see simple-api-mcp-stdio.py
"""

from praisonaiagents import Agent, MCP

try:
    # Create agent with MCP SSE connection
    search_agent = Agent(
        instructions="""You are a weather agent that can provide weather information for a given city.""",
        llm="openai/gpt-4o-mini",
        tools=MCP("http://localhost:8080/sse")
    )
    
    # Launch the API server
    print("Agent API started at http://localhost:3030/weather")
    print("Try: curl -X POST http://localhost:3030/weather -H 'Content-Type: application/json' -d '{\"message\": \"What is the weather in Paris?\"}'")
    
    search_agent.launch(path="/weather", port=3030)
    
except ConnectionError as e:
    print(f"\nError: {e}")
    print("\nPlease make sure the MCP SSE server is running first!")
    print("Run: python mcp-sse-direct-server.py")
    exit(1)