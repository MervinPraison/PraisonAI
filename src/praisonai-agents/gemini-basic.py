from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gemini/gemini-2.5-flash"
)
agent.start("Why sky is Blue?")