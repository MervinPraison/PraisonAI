from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help book apartments on Airbnb.""",
    tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
)

search_agent.start("Search apartment in Paris for 2 nights. 07/28 - 07/30 for 2 adults")