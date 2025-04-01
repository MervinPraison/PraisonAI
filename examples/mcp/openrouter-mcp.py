from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help book apartments on Airbnb.""",
    llm="openrouter/google/gemini-2.0-flash-exp:free",
    tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
)

search_agent.start("MUST USE airbnb_search Tool to Search. Search for Apartments in Paris for 2 nights. 04/28 - 04/30 for 2 adults. All Your Preference")