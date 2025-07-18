from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.0-flash",
    self_reflect=False,
    verbose=False,
    stream=True
)

# Use return_generator=True to get the raw generator for custom streaming handling
for chunk in agent.start("Write a report on about the history of the world", return_generator=True):
    print(chunk, end="", flush=True) 