from praisonaiagents import Agent, MCP
import os

# Use a single string command with Puppeteer configuration
puppeteer_agent = Agent(
    instructions="""You are a helpful assistant that can automate web browser interactions.
    Use the available tools when relevant to perform web automation tasks.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-puppeteer")
)

puppeteer_agent.start("Navigate to example.com and take a screenshot") 