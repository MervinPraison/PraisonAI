from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-5-nano"
)

agent.start("Why sky is Blue?")