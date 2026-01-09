"""Basic Agents (multi-agent) example with consolidated params."""
from praisonaiagents import Agent, Agents

# Create agents
writer = Agent(instructions="You write content.")
editor = Agent(instructions="You edit content.")

# Multi-agent with consolidated params
agents = Agents(
    agents=[writer, editor],
    memory=True,
    planning=True,
)

if __name__ == "__main__":
    result = agents.start("Write a haiku about AI")
    print(result)
