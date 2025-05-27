from praisonaiagents import Agent, MCP
import os

# Get the credentials path from environment
gdrive_credentials = os.getenv("GDRIVE_CREDENTIALS_PATH", "servers/gcp-oauth.keys.json")

# Use a single string command with Google Drive configuration
gdrive_agent = Agent(
    instructions="""You are a helpful assistant that can interact with Google Drive.
    Use the available tools when relevant to manage files and folders.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-gdrive",
              env={"GDRIVE_CREDENTIALS_PATH": gdrive_credentials})
)

gdrive_agent.start("List files in my Google Drive") 