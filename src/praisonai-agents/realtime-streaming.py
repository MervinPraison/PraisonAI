from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.0-flash",
    self_reflect=False,
    verbose=False,
    stream=True
)

for chunk in agent.start("Write a report on about the history of the world"):
    print(chunk, end="", flush=True) 