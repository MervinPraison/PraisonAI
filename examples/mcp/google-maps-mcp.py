from praisonaiagents import Agent, MCP
import os

# Get the API key from environment
maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

# Use a single string command with Google Maps configuration
maps_agent = Agent(
    instructions="""You are a helpful assistant that can interact with Google Maps.
    Use the available tools when relevant to handle location-based queries.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-google-maps",
              env={"GOOGLE_MAPS_API_KEY": maps_api_key})
)

maps_agent.start("Find nearby restaurants in London") 