"""
Example 4: Streaming with Chunk Processing

Process each chunk as it arrives - useful for real-time updates,
progress tracking, or custom formatting.

When to use: When you need to process/transform chunks before display.
"""
from praisonaiagents import Agent
import sys

agent = Agent(
    name="Counter",
    instructions="You count numbers clearly",
    output="stream"
)

chunk_count = 0
total_chars = 0

print("Streaming with chunk tracking:")
print("-" * 40)

for chunk in agent.start("Count from 1 to 10, one number per line"):
    chunk_count += 1
    total_chars += len(chunk)
    # Custom processing: uppercase the output
    sys.stdout.write(chunk.upper())
    sys.stdout.flush()

print("\n" + "-" * 40)
print(f"Stats: {chunk_count} chunks, {total_chars} characters")
