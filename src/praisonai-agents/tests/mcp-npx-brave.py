from praisonaiagents import Agent, MCP
import os

brave_api_key = os.getenv("BRAVE_API_KEY")

# Pass the environment variable directly to the MCP server
search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": brave_api_key}
    )
)

search_agent.start("Search more information about AI News")