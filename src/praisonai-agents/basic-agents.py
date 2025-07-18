from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)

# The start() method now automatically consumes the generator and displays the output
agent.start("Why sky is Blue?")