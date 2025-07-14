from praisonaiagents import Agent

agent = Agent(
    instructions="You are a competitor intelligence AI agent. "
                 "Help users analyze competitors, market trends, and business intelligence "
                 "to provide strategic insights and competitive advantages.",
    llm="xai/grok-4"
)

response = agent.start(
    "I need to analyze my main competitor's pricing strategy and market positioning. "
    "Can you help me gather insights?"
) 