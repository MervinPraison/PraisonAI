#!/usr/bin/env python3
"""Test script to verify the Gemini JSON parsing fix."""

from praisonaiagents import Agent

# Test with minimal configuration to isolate the issue
llm_config = {
    "model": "gemini/gemini-1.5-flash-latest",
    "temperature": 0.7,
    "max_tokens": 500,
}

# Create agent with self-reflection enabled
agent = Agent(
    instructions="You are a helpful assistant. Be concise and clear.",
    llm=llm_config,
    verbose=True,
    self_reflect=True,
    max_reflect=2,
    min_reflect=1
)

# Test with a simple prompt
print("Testing Gemini with self-reflection...")
try:
    response = agent.start("What is 2+2? Explain briefly.")
    print(f"\nFinal response: {response}")
    print("\nTest completed successfully!")
except Exception as e:
    print(f"\nError occurred: {e}")
    import traceback
    traceback.print_exc()
