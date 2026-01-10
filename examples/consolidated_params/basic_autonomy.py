"""
Basic Autonomy Example - Agent-Centric API

Demonstrates autonomy with consolidated params.
Presets: suggest, auto_edit, full_auto
"""

from praisonaiagents import Agent

# Basic: Enable autonomy with preset
agent = Agent(
    instructions="You are an autonomous assistant.",
    autonomy="suggest",  # Presets: suggest, auto_edit, full_auto
)

if __name__ == "__main__":
    response = agent.start("Help me organize my project files.")
    print(response)
