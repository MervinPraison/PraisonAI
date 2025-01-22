from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-1.5-flash-8b",
    self_reflect=True,
    verbose=True
)

agent.start("Why sky is Blue?")