from praisonaiagents import Agent, Agents, MCP

airbnb_agent = Agent(
    instructions="""Search for Apartments in Paris for 2 nights on Airbnb. 04/28 - 04/30 for 2 adults""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
)

whatsapp_agent = Agent(
    instructions="""Send AirBnb Search Result to 'Mervin Praison'""",
    llm="gpt-4o-mini",
    tools=MCP("python /Users/praison/whatsapp-mcp/whatsapp-mcp-server/main.py")
)

agents = Agents(agents=[airbnb_agent, whatsapp_agent])

agents.start()