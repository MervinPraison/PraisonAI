"""Basic Agent example with consolidated params."""
from praisonaiagents import Agent

# Minimal agent with memory
agent = Agent(
    instructions="You are a helpful assistant.",
    memory=True,
)

if __name__ == "__main__":
    response = agent.chat("Hello!")
    print(response)
