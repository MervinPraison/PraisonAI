"""
Basic Caching Configuration Example

Demonstrates using caching for response and prompt caching.
"""
import os
from praisonaiagents import Agent, CachingConfig

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Default caching (enabled)
agent_cached = Agent(
    instructions="You are a helpful assistant.",
    caching=True,
)

# Disable caching
agent_no_cache = Agent(
    instructions="You are a helpful assistant.",
    caching=False,
)

# Custom caching configuration
agent_custom = Agent(
    instructions="You are a helpful assistant.",
    caching=CachingConfig(
        enabled=True,
        prompt_caching=True,  # Enable prompt caching for supported providers
    ),
)

if __name__ == "__main__":
    print("Testing CachingConfig...")
    
    print(f"Cached agent cache: {agent_cached.cache}")
    print(f"No-cache agent cache: {agent_no_cache.cache}")
    print(f"Custom agent cache: {agent_custom.cache}")
    
    result = agent_cached.chat("What is caching?")
    print(f"Result: {result}")
    
    print("\nCachingConfig tests passed!")
