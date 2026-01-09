"""
Advanced Output + Execution Example - Agent-Centric API

Demonstrates preset + override array syntax.
"""

from praisonaiagents import Agent

# Advanced: Preset with overrides using array syntax
agent = Agent(
    instructions="You are a helpful assistant.",
    output=["verbose", {"stream": True, "metrics": True}],
    execution=["thorough", {"max_iter": 30}],
)

response = agent.start("Explain quantum computing in simple terms.")
print(response)
