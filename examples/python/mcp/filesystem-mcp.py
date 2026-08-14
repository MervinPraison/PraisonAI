from praisonaiagents import Agent, MCP
import os

# Define allowed directories for filesystem access
allowed_dirs = [
    "/Users/username/Desktop",
    "/path/to/other/allowed/dir"
]

# Pass the executable as the first token and the allowed directories as args
filesystem_agent = Agent(
    instructions="""You are a helpful assistant that can interact with the filesystem.
    Use the available tools when relevant to manage files and directories.""",
    llm="gpt-4o-mini",
    tools=MCP("npx", args=["-y", "@modelcontextprotocol/server-filesystem", *allowed_dirs])
)

filesystem_agent.start("List files in the allowed directories") 