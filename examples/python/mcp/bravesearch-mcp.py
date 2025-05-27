from praisonaiagents import Agent, MCP
import os

# Use the API key from environment or set it directly
brave_api_key = os.getenv("BRAVE_API_KEY")

# Use a single string command with environment variables
search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-brave-search", env={"BRAVE_API_KEY": brave_api_key})
)

search_agent.start("Search more information about AI News")