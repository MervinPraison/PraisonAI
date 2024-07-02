import os
import yaml
from praisonai.cli import PraisonAI

# Example agent_yaml content
agent_yaml = """
framework: "crewai"
topic: "Space Exploration"

roles:
  astronomer:
    role: "Space Researcher"
    goal: "Discover new insights about {topic}"
    backstory: "You are a curious and dedicated astronomer with a passion for unraveling the mysteries of the cosmos."
    tasks:
      investigate_exoplanets:
        description: "Research and compile information about exoplanets discovered in the last decade."
        expected_output: "A summarized report on exoplanet discoveries, including their size, potential habitability, and distance from Earth."
"""

# Create a PraisonAI instance with the agent_yaml content
praison_ai = PraisonAI(agent_yaml=agent_yaml)

# Run PraisonAI
result = praison_ai.main()

# Print the result
print(result)