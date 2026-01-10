"""
Basic Reflection Example - Agent-Centric API

Demonstrates reflection (self-reflect) with consolidated params.
Presets: minimal, standard, thorough
"""

from praisonaiagents import Agent

# Basic: Enable reflection with preset
agent = Agent(
    instructions="You are a helpful assistant that reflects on your answers.",
    reflection="standard",  # Presets: minimal, standard, thorough
)

if __name__ == "__main__":
    response = agent.start("Explain quantum computing in simple terms.")
    print(response)
