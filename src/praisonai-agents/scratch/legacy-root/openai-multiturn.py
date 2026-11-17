from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)
agent.start("Why sky is Blue?")
agent.start("What was my previous question?")