from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.0-flash",
    reflection=False,
    output="stream"
)

# Use return_generator=True to get the raw generator for custom streaming handling
for chunk in agent.start("Write a report on about the history of the world"):
    print(chunk, end="", flush=True) 