from praisonaiagents import Agent, MCP
import os

# Get Everart API key from environment
everart_api_key = os.getenv("EVERART_API_KEY")

# Use a single string command with Everart configuration
everart_agent = Agent(
    instructions="""You are a helpful assistant that can interact with Everart.
    Use the available tools when relevant to generate and manage art.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-everart",
              env={"EVERART_API_KEY": everart_api_key})
)

everart_agent.start("Generate an artistic image of a sunset") 