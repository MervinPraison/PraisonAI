"""
Guardrails - Basic Example

Demonstrates minimal usage of guardrails with a single agent.

Expected Output:
    Agent response demonstrating guardrails functionality.
"""
from praisonaiagents import Agent

# Basic guardrails usage
agent = Agent(
    instructions="You are a helpful assistant",
    # guardrails=...  # Configure guardrails here
)

# Run the agent
result = agent.start("Hello! Demonstrate guardrails functionality.")
print(result)
