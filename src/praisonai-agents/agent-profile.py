"""
Streaming Example with Profiling

Key Points:
1. output="stream" preset enables streaming by default
2. stream=True in start() is redundant when using output="stream" (but doesn't hurt)
3. Profiler.enable() MUST be called before profiling works
4. Use Profiler.streaming() context manager for TTFT metrics
"""
from praisonai.profiler import Profiler, profile, profile_imports

# IMPORTANT: Enable profiler BEFORE any profiling operations
Profiler.enable()

# Profile imports
with profile_imports():
    from praisonaiagents import Agent

@profile
def main():
    agent = Agent(
        instructions="You are a helpful assistant",
        output="stream"  # This already enables streaming
    )

    print("\nStreaming response:")
    print("-" * 40)
    
    # Use Profiler.streaming() to track TTFT (Time To First Token)
    with Profiler.streaming("llm_stream") as tracker:
        first_chunk = True
        for chunk in agent.start("Write a short paragraph about the history of computing"):
            if first_chunk:
                tracker.first_token()  # Mark TTFT
                first_chunk = False
            tracker.chunk()  # Count chunks
            print(chunk, end="", flush=True)
    
    print("\n" + "-" * 40)

# Run with profiling blocks
with Profiler.block("full_workflow"):
    with Profiler.block("setup"):
        pass
    
    with Profiler.block("execution"):
        result = main()
    
    with Profiler.block("cleanup"):
        pass

# Generate report
Profiler.report()

# Show streaming-specific stats
streaming_records = Profiler.get_streaming_records()
if streaming_records:
    print("\nStreaming Metrics:")
    for record in streaming_records:
        print(f"  {record.name}: TTFT={record.ttft_ms:.2f}ms, Total={record.total_ms:.2f}ms, Chunks={record.chunk_count}")

stats = Profiler.get_statistics()
print(f"\nMedian execution time: {stats['p50']:.2f}ms")