from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help search the web.""",
    llm="gpt-4o-mini",
    tools=MCP("http://localhost:8931/sse")
)

search_agent.start("Find about Praison AI")
