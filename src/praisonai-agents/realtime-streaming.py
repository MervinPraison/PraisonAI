from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-3.5-turbo",  # Use basic model for testing
    self_reflect=False,
    verbose=False,
    stream=True
)

# Use return_generator=True to get the raw generator for custom streaming handling
for chunk in agent.start("Write a report on about the history of the world"):
    print(chunk, end="", flush=True) 