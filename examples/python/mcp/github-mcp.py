from praisonaiagents import Agent, MCP
import os

# Use the API key from environment or set it directly
github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")

# Use a single string command with environment variables
github_agent = Agent(
    instructions="""You are a helpful assistant that can interact with GitHub.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-github", env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token})
)

github_agent.start("List my GitHub repositories") 