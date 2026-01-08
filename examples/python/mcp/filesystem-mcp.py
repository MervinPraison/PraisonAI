from praisonaiagents import Agent, MCP
import os

# Define allowed directories for filesystem access
allowed_dirs = [
    "/Users/username/Desktop",
    "/path/to/other/allowed/dir"
]

# Use a single string command with allowed directories
filesystem_agent = Agent(
    instructions="""You are a helpful assistant that can interact with the filesystem.
    Use the available tools when relevant to manage files and directories.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-filesystem", args=allowed_dirs)
)

filesystem_agent.start("List files in the allowed directories") 