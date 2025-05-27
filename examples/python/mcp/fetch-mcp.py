from praisonaiagents import Agent, MCP
import os

# pip install mcp-server-fetch
# Use a single string command with Fetch configuration
fetch_agent = Agent(
    instructions="""You are a helpful assistant that can fetch and process web content.
    Use the available tools when relevant to retrieve and convert web pages to markdown.""",
    llm="gpt-4o-mini",
    tools=MCP("python -m mcp_server_fetch")
)

fetch_agent.start("Fetch and convert the content from https://example.com to markdown") 