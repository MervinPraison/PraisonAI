from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help book apartments on Airbnb.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="npx",
        args=[
            "-y",
            "@openbnb/mcp-server-airbnb",
            "--ignore-robots-txt",
        ]
    )
)

search_agent.start("I want to book an apartment in Paris for 2 nights. 03/28 - 03/30 for 2 adults")