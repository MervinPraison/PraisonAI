"""
Example 1: Basic Streaming with output="stream" preset

This is the simplest way to enable streaming. The "stream" preset
automatically sets stream=True along with verbose=True and markdown=True.

When to use: When you want streaming enabled by default for all agent.start() calls.
"""
from praisonaiagents import Agent

agent = Agent(
    name="Storyteller",
    instructions="You are a creative storyteller",
    output="stream"  # Enables streaming by default
)

print("Streaming response:")
for chunk in agent.start("Write a haiku about coding"):
    print(chunk, end="", flush=True)
print("\n")
