from praisonaiagents import Agent, MCP

qa_agent = Agent(
    instructions="""You are a Question Answering Agent.""",
    llm="openai/gpt-4o-mini",
    tools=MCP("http://localhost:8080/agents/sse")
)

qa_agent.start("AI in 2025")