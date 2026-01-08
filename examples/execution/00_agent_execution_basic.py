"""
Basic Execution Configuration Example

Demonstrates using execution presets for quick configuration.
"""
import os
from praisonaiagents import Agent

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Default execution (max_iter=20, max_retry_limit=2)
agent_default = Agent(
    instructions="You are a helpful assistant.",
)

# Fast execution - fewer iterations, quick responses
agent_fast = Agent(
    instructions="You are a helpful assistant.",
    execution="fast",
)

# Thorough execution - more iterations, comprehensive responses
agent_thorough = Agent(
    instructions="You are a research assistant.",
    execution="thorough",
)

# Unlimited execution - for complex tasks
agent_unlimited = Agent(
    instructions="You are a complex problem solver.",
    execution="unlimited",
)

if __name__ == "__main__":
    print("Testing execution presets...")
    
    print(f"Default agent max_iter: {agent_default.max_iter}")
    print(f"Fast agent max_iter: {agent_fast.max_iter}")
    print(f"Thorough agent max_iter: {agent_thorough.max_iter}")
    print(f"Unlimited agent max_iter: {agent_unlimited.max_iter}")
    
    # Test fast agent
    print("\n--- Fast Execution ---")
    result = agent_fast.chat("What is the capital of France?")
    print(f"Result: {result}")
    
    print("\nAll execution preset tests passed!")
