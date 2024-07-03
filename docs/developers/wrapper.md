# Include praisonai package in your project

## Option 1: Using RAW YAML

```python
from praisonai import PraisonAI

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
```

## Option 2: Using separate agents.yaml file


Note: Please create agents.yaml file before hand. 

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()

if __name__ == "__main__":
    basic()
```

## Other options

```python
from praisonai import PraisonAI

def basic(): # Basic Mode
    praison_ai = PraisonAI(agent_file="agents.yaml")
    praison_ai.main()
    
def advanced(): # Advanced Mode with options
    praison_ai = PraisonAI(
        agent_file="agents.yaml",
        framework="autogen",
    )
    praison_ai.main()
    
def auto(): # Full Automatic Mode
    praison_ai = PraisonAI(
        auto="Create a movie script about car in mars",
        framework="autogen"
    )
    print(praison_ai.framework)
    praison_ai.main()

if __name__ == "__main__":
    basic()
    advanced()
    auto()
```

