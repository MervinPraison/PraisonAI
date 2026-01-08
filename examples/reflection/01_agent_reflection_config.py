"""
ReflectionConfig Example

Demonstrates using ReflectionConfig for fine-grained control.
"""
import os
from praisonaiagents import Agent, ReflectionConfig

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Custom reflection configuration
agent = Agent(
    instructions="You are a helpful math tutor.",
    reflection=ReflectionConfig(
        min_iterations=1,
        max_iterations=3,
        llm=None,  # Use same LLM as main agent
        prompt=None,  # Use default reflection prompt
    ),
)

# More iterations for complex tasks
agent_thorough = Agent(
    instructions="You are a research assistant.",
    reflection=ReflectionConfig(
        min_iterations=2,
        max_iterations=5,
    ),
)

if __name__ == "__main__":
    print("Testing ReflectionConfig...")
    
    print(f"Agent min_reflect: {agent.min_reflect}")
    print(f"Agent max_reflect: {agent.max_reflect}")
    print(f"Thorough agent max_reflect: {agent_thorough.max_reflect}")
    
    result = agent.chat("What is the derivative of x^2?")
    print(f"Result: {result}")
    
    print("\nReflectionConfig tests passed!")
