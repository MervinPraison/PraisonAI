from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    self_reflect=False,
    verbose=True,
    stream=True
)

result = agent.start("Write a long report on about the history of the world")
print(result)