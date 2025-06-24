from praisonaiagents import Agent, MCP
import os

# pip install mcp-server-time
# Use a single string command with Time Server configuration
time_agent = Agent(
    instructions="""You are a helpful assistant that can handle time-related operations.
    Use the available tools when relevant to manage timezone conversions and time information.""",
    llm="gpt-4o-mini",
    tools=MCP("python -m mcp_server_time --local-timezone=America/New_York")
)

time_agent.start("Get the current time in New York and convert it to UTC") 