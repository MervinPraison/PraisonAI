"""
Basic Planning Example - Agent-Centric API

Demonstrates planning with consolidated params.
Presets: reasoning, read_only, auto
"""

from praisonaiagents import Agent

# Basic: Enable planning with preset
agent = Agent(
    instructions="You are a strategic planner.",
    planning="reasoning",  # Presets: reasoning, read_only, auto
)

if __name__ == "__main__":
    response = agent.start("Plan a 3-day trip to Tokyo.")
    print(response)
