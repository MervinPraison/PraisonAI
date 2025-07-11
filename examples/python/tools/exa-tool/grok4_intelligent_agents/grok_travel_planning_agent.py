from praisonaiagents import Agent

agent = Agent(
    instructions="You are a travel planning AI agent. Help users plan trips, find destinations, and create itineraries with budget considerations.",
    llm="xai/grok-4"
)

response = agent.start("I want to plan a 7-day trip to Europe with a budget of $3000. What are my best options?") 