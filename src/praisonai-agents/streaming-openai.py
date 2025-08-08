from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-5-nano",
    stream=True
)

for chunk in agent.start("Write a report on about the history of the world"):
    print(chunk, end="", flush=True)