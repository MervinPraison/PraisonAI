from praisonaiagents import Agent, MCP
import os

# Databutton API key
databutton_api_key = os.getenv("DATABUTTON_API_KEY")

# Create databutton agent
databutton_agent = Agent(
    instructions="""You are a helpful assistant that can interact with Databutton.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP("uvx databutton-app-mcp@latest", env={"DATABUTTON_API_KEY": databutton_api_key})
)

databutton_agent.start("Get the current stock price for AAPL, Tesla, and Amazon")
