from praisonaiagents import Agent, MCP
import os

# pip install mcp-server-sentry
# Get Sentry auth token from environment
sentry_token = os.getenv("SENTRY_AUTH_TOKEN")

# Use a single string command with Sentry configuration
sentry_agent = Agent(
    instructions="""You are a helpful assistant that can analyze Sentry error reports.
    Use the available tools when relevant to inspect and debug application issues.""",
    llm="gpt-4o-mini",
    tools=MCP("python -m mcp_server_sentry --auth-token", args=[sentry_token])
)

sentry_agent.start("Analyze the most recent critical error in Sentry") 