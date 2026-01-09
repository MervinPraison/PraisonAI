"""
Basic Memory Example - Agent-Centric API

Demonstrates the simplest memory usage with consolidated params.
"""

from praisonaiagents import Agent

# Basic: Enable memory with preset
agent = Agent(
    instructions="You are a helpful assistant with memory.",
    memory="sqlite",  # Preset: sqlite, redis, postgres, file
)

# Run a simple task
response = agent.start("Remember that my favorite color is blue.")
print(response)

# Follow-up to test memory
response = agent.start("What is my favorite color?")
print(response)
