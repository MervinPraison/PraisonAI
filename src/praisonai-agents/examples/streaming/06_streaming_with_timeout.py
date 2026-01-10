"""
Example 6: Streaming with Timeout/Early Stop

Implement timeout or early stopping for streaming responses.
Useful for limiting response length or handling slow responses.

When to use: When you need to limit streaming duration or length.
"""
from praisonaiagents import Agent
import time

agent = Agent(
    name="Storyteller",
    instructions="You write long, detailed stories",
    output="stream"
)

MAX_CHARS = 200
MAX_TIME = 5.0  # seconds

print(f"Streaming with limits: max {MAX_CHARS} chars or {MAX_TIME}s")
print("-" * 40)

start_time = time.time()
total_chars = 0
stopped_early = False

for chunk in agent.start("Write a very long story about a dragon"):
    elapsed = time.time() - start_time
    
    # Check time limit
    if elapsed > MAX_TIME:
        print("\n[TIMEOUT - stopped after {:.1f}s]".format(elapsed))
        stopped_early = True
        break
    
    # Check character limit
    if total_chars + len(chunk) > MAX_CHARS:
        # Print partial chunk up to limit
        remaining = MAX_CHARS - total_chars
        print(chunk[:remaining], end="", flush=True)
        print("\n[MAX CHARS - stopped at {} chars]".format(MAX_CHARS))
        stopped_early = True
        break
    
    print(chunk, end="", flush=True)
    total_chars += len(chunk)

if not stopped_early:
    print("\n[Completed normally]")

print("-" * 40)
print(f"Total: {total_chars} chars in {time.time() - start_time:.2f}s")
