"""
WebConfig Example

Demonstrates using WebConfig for fine-grained control.
"""
import os
from praisonaiagents import Agent

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Custom web configuration
agent = Agent(
    instructions="You are a research assistant.",
    web="search_only",
)

# Search only (no fetch)
agent_search_only = Agent(
    instructions="You are a research assistant.",
    web="search_only",
)

if __name__ == "__main__":
    print("Testing WebConfig...")
    
    print(f"Agent web_search: {agent.web_search}")
    print(f"Agent web_fetch: {agent.web_fetch}")
    print(f"Search-only agent web_fetch: {agent_search_only.web_fetch}")
    
    result = agent.chat("What is machine learning?")
    print(f"Result: {result}")
    
    print("\nWebConfig tests passed!")
