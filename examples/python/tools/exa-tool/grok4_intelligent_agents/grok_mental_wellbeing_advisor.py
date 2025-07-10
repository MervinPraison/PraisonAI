from praisonaiagents import Agent

agent = Agent(
    instructions="You are a mental wellbeing AI advisor. Provide supportive guidance and wellness tips.",
    llm="xai/grok-4"
)

response = agent.start("I've been feeling stressed at work lately. Any tips for managing stress?")