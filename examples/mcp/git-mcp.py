from praisonaiagents import Agent, MCP
import os

# pip install mcp-server-git
# Get Git credentials from environment
git_username = os.getenv("GIT_USERNAME")
git_email = os.getenv("GIT_EMAIL")
git_token = os.getenv("GIT_TOKEN")  # For private repos

# Use a single string command with Git configuration
git_agent = Agent(
    instructions="""You are a helpful assistant that can perform Git operations.
    Use the available tools when relevant to manage repositories, commits, and branches.""",
    llm="gpt-4o-mini",
    tools=MCP("python -m mcp_server_git",
              env={
                  "GIT_USERNAME": git_username,
                  "GIT_EMAIL": git_email,
                  "GIT_TOKEN": git_token
              })
)

git_agent.start("Clone and analyze the repository at https://github.com/modelcontextprotocol/servers") 