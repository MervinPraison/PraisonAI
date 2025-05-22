from praisonaiagents import Agent, MCP

tweet_agent = Agent(
    instructions="""You are a Tweet Formatter Agent.""",
    tools=MCP("http://localhost:8080/sse")
)

tweet_agent.start("AI in Healthcare")