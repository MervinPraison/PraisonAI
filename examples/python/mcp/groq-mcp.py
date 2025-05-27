from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help book apartments on Airbnb.""",
    llm="groq/llama-3.2-90b-vision-preview",
    tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
)

search_agent.start("MUST USE airbnb_search Tool to Search. Search for Apartments in Paris for 2 nights. 04/28 - 04/30 for 2 adults. All Your Preference")