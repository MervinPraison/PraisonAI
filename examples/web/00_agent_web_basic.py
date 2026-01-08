"""
Basic Web Configuration Example

Demonstrates using web search and fetch capabilities.
"""
import os
from praisonaiagents import Agent

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Enable web search and fetch
agent = Agent(
    instructions="You are a research assistant with web access.",
    web=True,
)

# Disable web (default)
agent_no_web = Agent(
    instructions="You are a helpful assistant.",
    web=False,
)

if __name__ == "__main__":
    print("Testing web configuration...")
    
    print(f"Web agent web_search: {agent.web_search}")
    print(f"Web agent web_fetch: {agent.web_fetch}")
    print(f"No-web agent web_search: {agent_no_web.web_search}")
    
    # Note: This requires a model that supports web search
    result = agent.chat("What is the current weather concept?")
    print(f"Result: {result}")
    
    print("\nWeb configuration tests passed!")
