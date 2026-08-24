"""Basic memory example - minimal usage."""
from praisonaiagents import Agent

# Simple enable (uses default file-based memory)
agent = Agent(
    instructions="You are a helpful assistant with memory.",
    memory=True,
)

# With preset
agent_sqlite = Agent(
    instructions="You are a helpful assistant.",
    memory="sqlite",  # Uses sqlite preset
)

# With URL
agent_mongo = Agent(
    instructions="You are a helpful assistant.",
    memory="mongodb://localhost/mydb",  # URL auto-detected
)

if __name__ == "__main__":
    response = agent.chat("Remember that my favorite color is blue.")
    print(response)
