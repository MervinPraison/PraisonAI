"""
Basic Caching Example - Agent-Centric API

Demonstrates caching with consolidated params.
Presets: enabled, disabled, prompt
"""

from praisonaiagents import Agent

# Basic: Enable caching with preset
agent = Agent(
    instructions="You are a helpful assistant with caching enabled.",
    caching="prompt",  # Presets: enabled, disabled, prompt
)

if __name__ == "__main__":
    # First call - will cache
    response = agent.start("What is the capital of France?")
    print(response)
    
    # Second call - may use cache
    response = agent.start("What is the capital of France?")
    print(response)
