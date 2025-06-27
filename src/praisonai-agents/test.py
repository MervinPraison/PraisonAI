from dotenv import load_dotenv
from praisonaiagents import Agent, MCP

# Load .env before importing anything else
load_dotenv()

# Define allowed directories for filesystem access
allowed_dirs = [
    "/Users/praison/praisonai-package/src/praisonai-agents",
]

# Use the correct pattern from filesystem MCP documentation
filesystem_agent = Agent(
    instructions="""You are a helpful assistant that can interact with the filesystem.
    Use the available tools when relevant to manage files and directories.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs
    )
)

filesystem_agent.start("List files in /Users/praison/praisonai-package/src/praisonai-agents directory using MCP list_files")