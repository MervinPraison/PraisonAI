"""
Basic Output Example - Agent-Centric API

Demonstrates output preset usage.
"""

from praisonaiagents import Agent

# Basic: Use verbose output preset
agent = Agent(
    instructions="You are a helpful assistant.",
    output="verbose",  # Presets: minimal, normal, verbose, debug, silent
)

response = agent.start("What is 2 + 2?")
print(response)
