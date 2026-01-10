"""
Example 3: Silent Streaming (no verbose output)

Combine output="silent" with stream=True in start() for clean streaming
without any verbose agent output.

When to use: When you want pure streaming output without status messages.
"""
from praisonaiagents import Agent

agent = Agent(
    name="Writer",
    instructions="You are a concise writer",
    output="silent"  # No verbose output
)

print("Silent streaming (clean output):")
for chunk in agent.start("Write a one-sentence joke", stream=True):
    print(chunk, end="", flush=True)
print("\n")
