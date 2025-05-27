from praisonaiagents import Agent, MCP
import os

# Get the memory file path from environment
memory_file_path = os.getenv("MEMORY_FILE_PATH", "/path/to/custom/memory.json")

# Use a single string command with Memory configuration
memory_agent = Agent(
    instructions="""You are a helpful assistant that can store and retrieve information.
    Use the available tools when relevant to manage memory operations.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-memory",
              env={"MEMORY_FILE_PATH": memory_file_path})
)

memory_agent.start("Store this conversation in memory") 