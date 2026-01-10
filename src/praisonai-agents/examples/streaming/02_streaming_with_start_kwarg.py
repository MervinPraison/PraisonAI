"""
Example 2: Streaming with start(stream=True)

Use stream=True in start() to enable streaming for a specific call,
regardless of the output preset used.

When to use: When you want to control streaming per-call, not globally.
"""
from praisonaiagents import Agent

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant",
    output="verbose"  # Not streaming by default
)

# Non-streaming call
print("Non-streaming response:")
response = agent.start("Say hello in one word")
print(response)
print()

# Streaming call - override with stream=True
print("Streaming response:")
for chunk in agent.start("Count from 1 to 5", stream=True):
    print(chunk, end="", flush=True)
print("\n")
