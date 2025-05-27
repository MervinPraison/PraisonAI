from praisonaiagents import Agent, MCP
import os

# Use the API token and URL from environment or set directly
gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
gitlab_api_url = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")

# Use a single string command with environment variables
gitlab_agent = Agent(
    instructions="""You are a helpful assistant that can interact with GitLab.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-gitlab", 
              env={
                  "GITLAB_PERSONAL_ACCESS_TOKEN": gitlab_token,
                  "GITLAB_API_URL": gitlab_api_url
              })
)

gitlab_agent.start("List my GitLab projects") 