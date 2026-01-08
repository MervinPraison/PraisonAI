from praisonaiagents import Agent, MCP
import os

# Use a single string command with Sequential Thinking configuration
sequential_agent = Agent(
    instructions="""You are a helpful assistant that can break down complex problems.
    Use the available tools when relevant to perform step-by-step analysis.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking")
)

sequential_agent.start("Break down the process of making a cup of tea") 