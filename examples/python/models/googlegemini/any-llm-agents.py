from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    model="gemini/gemini-1.5-flash-8b",
    reflection=True)

agent.start("Why sky is Blue?")