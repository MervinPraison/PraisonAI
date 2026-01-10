"""
Example 10: Streaming vs Non-Streaming Comparison

Compare streaming and non-streaming modes side by side.
Shows the difference in user experience and timing.

When to use: To understand when to use streaming vs non-streaming.
"""
from praisonaiagents import Agent
import time

# Create two agents with different output modes
streaming_agent = Agent(
    name="StreamingAgent",
    instructions="You write brief responses",
    output="stream"
)

non_streaming_agent = Agent(
    name="NonStreamingAgent", 
    instructions="You write brief responses",
    output="verbose"
)

prompt = "Write a 2-sentence summary of machine learning"

# Non-streaming: Wait for full response
print("=" * 50)
print("NON-STREAMING MODE")
print("=" * 50)
start = time.time()
response = non_streaming_agent.start(prompt, stream=False)
end = time.time()
print(f"Response: {response}")
print(f"Time to first output: {end - start:.2f}s (full response)")
print()

# Streaming: See output as it's generated
print("=" * 50)
print("STREAMING MODE")
print("=" * 50)
start = time.time()
first_chunk_time = None
for chunk in streaming_agent.start(prompt):
    if first_chunk_time is None:
        first_chunk_time = time.time()
    print(chunk, end="", flush=True)
end = time.time()
print()
print(f"Time to first chunk: {first_chunk_time - start:.2f}s")
print(f"Total time: {end - start:.2f}s")

print()
print("=" * 50)
print("SUMMARY")
print("=" * 50)
print("""
Streaming Benefits:
- Faster perceived response (see output immediately)
- Better UX for long responses
- Can process/display chunks in real-time

Non-Streaming Benefits:
- Simpler code (just get the response)
- Better for programmatic processing
- No need to handle generators
""")
