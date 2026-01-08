"""
Basic Reflection Configuration Example

Demonstrates using reflection for self-improvement.
"""
import os
from praisonaiagents import Agent

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Enable reflection with defaults
agent = Agent(
    instructions="You are a helpful math tutor.",
    reflection=True,
)

# Disable reflection (default)
agent_no_reflect = Agent(
    instructions="You are a helpful assistant.",
    reflection=False,
)

if __name__ == "__main__":
    print("Testing reflection...")
    
    print(f"Reflection agent self_reflect: {agent.self_reflect}")
    print(f"No-reflect agent self_reflect: {agent_no_reflect.self_reflect}")
    
    result = agent.chat("Solve: What is 15% of 80?")
    print(f"Result: {result}")
    
    print("\nReflection tests passed!")
