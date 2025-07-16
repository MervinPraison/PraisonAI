from praisonaiagents import Agent

agent = Agent(
    instructions="You are a meeting productivity AI agent. Help optimize meeting efficiency and follow-up actions.",
    llm="xai/grok-4"
)

response = agent.start("I have a team meeting tomorrow. How can I make it more productive?")