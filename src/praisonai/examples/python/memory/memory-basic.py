"""
Memory - Basic Example

Demonstrates minimal usage of memory with a single agent.

Expected Output:
    Agent response demonstrating memory functionality.
"""
from praisonaiagents import Agent, Memory

# Basic memory usage
memory = Memory()  # Initialize memory for the agent

agent = Agent(
    instructions="You are a helpful assistant",
    memory=memory  # Configure memory here
)

# Run the agent
result = agent.start("Hello! Demonstrate memory functionality.")
print(result)
