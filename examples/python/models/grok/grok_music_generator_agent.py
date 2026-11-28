from praisonaiagents import Agent

agent = Agent(
    instructions="You are a music generation AI agent. Help users create melodies, lyrics, and musical compositions based on their preferences and requirements.",
    model="xai/grok-4"
)

response = agent.start("I need a catchy jingle for my coffee shop. Can you help me create one?") 