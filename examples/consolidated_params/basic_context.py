"""
Basic Context Example - Agent-Centric API

Demonstrates context management with consolidated params.
Presets: sliding_window, summarize, truncate
"""

from praisonaiagents import Agent

# Basic: Enable context management with preset
agent = Agent(
    instructions="You are a helpful assistant with context management.",
    context="sliding_window",  # Presets: sliding_window, summarize, truncate
)

if __name__ == "__main__":
    response = agent.start("Tell me a long story about a dragon.")
    print(response)
