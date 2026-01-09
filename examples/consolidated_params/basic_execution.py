"""
Basic Execution Example - Agent-Centric API

Demonstrates execution preset usage.
"""

from praisonaiagents import Agent

# Basic: Use fast execution preset
agent = Agent(
    instructions="You are a helpful assistant.",
    execution="fast",  # Presets: fast, balanced, thorough, unlimited
)

response = agent.start("What is the capital of France?")
print(response)
