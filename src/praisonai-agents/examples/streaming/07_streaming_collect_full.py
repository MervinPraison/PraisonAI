"""
Example 7: Streaming with Full Response Collection

Stream output to user while also collecting the full response.
Useful when you need both real-time display AND the complete response.

When to use: When you need to display AND process the full response.
"""
from praisonaiagents import Agent

agent = Agent(
    name="Analyst",
    instructions="You provide brief analysis",
    output="stream"
)

print("Streaming while collecting full response:")
print("-" * 40)

# Collect chunks while streaming
chunks = []
for chunk in agent.start("List 3 benefits of Python"):
    chunks.append(chunk)
    print(chunk, end="", flush=True)

# Join to get full response
full_response = "".join(chunks)

print("\n" + "-" * 40)
print(f"\nFull response collected ({len(full_response)} chars):")
print(f"Word count: {len(full_response.split())}")
print(f"Line count: {len(full_response.splitlines())}")
