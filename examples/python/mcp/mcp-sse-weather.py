from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You are a weather agent that can provide weather information for a given city.""",
    llm="openai/gpt-4o-mini",
    tools=MCP("http://localhost:8080/sse")
)

search_agent.start("What is the weather in London?")