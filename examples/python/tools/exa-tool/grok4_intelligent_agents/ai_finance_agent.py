from praisonaiagents import Agent

agent = Agent(
    instructions="You are a finance AI agent. "
                 "Help users with financial analysis, investment strategies, "
                 "budget planning, and market trend analysis for informed decision making.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to analyze my investment portfolio and create a diversification strategy. "
    "Can you help me optimize my financial planning?"
) 