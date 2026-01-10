"""
Example 8: Async Streaming

Use async streaming for non-blocking operations.
Useful in async applications like web servers or async pipelines.

When to use: In async/await contexts like FastAPI, aiohttp, etc.
"""
from praisonaiagents import Agent
import asyncio

agent = Agent(
    name="AsyncHelper",
    instructions="You are a helpful assistant",
    output="stream"
)

async def stream_response():
    """Async wrapper for streaming."""
    print("Async streaming example:")
    print("-" * 40)
    
    # Note: agent.start() returns a sync generator
    # For true async streaming, use agent.astart() if available
    # This example shows how to use sync streaming in async context
    
    loop = asyncio.get_event_loop()
    
    def sync_stream():
        result = []
        for chunk in agent.start("Say hello in 3 languages"):
            result.append(chunk)
            print(chunk, end="", flush=True)
        return result
    
    # Run sync streaming in executor to not block
    chunks = await loop.run_in_executor(None, sync_stream)
    
    print("\n" + "-" * 40)
    print(f"Collected {len(chunks)} chunks")

if __name__ == "__main__":
    asyncio.run(stream_response())
