"""
Basic Profiling Example for PraisonAI

This example demonstrates how to use the profiler programmatically
to measure agent performance.

Run with:
    python basic_profiling.py
"""

import os

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

from praisonai.cli.features.profiler import (
    ProfilerConfig,
    QueryProfiler,
    format_profile_report,
)


def main():
    """Run a profiled query and display results."""
    
    # Configure profiler
    config = ProfilerConfig(
        deep=False,          # Set True for detailed call tracing (slower)
        limit=15,            # Show top 15 functions
        show_files=True,     # Group by file
        first_token=False,   # Track time to first token (for streaming)
    )
    
    # Create profiler
    profiler = QueryProfiler(config)
    
    # Run profiled query
    print("🔬 Running profiled query...")
    result = profiler.profile_query(
        prompt="What is 2+2?",
        model=None,  # Use default model
        stream=False,
    )
    
    # Print formatted report
    print("\n" + format_profile_report(result, config))
    
    # Access timing data programmatically
    print("\n📊 Timing Summary:")
    print(f"  Imports:        {result.timing.imports_ms:>10.2f} ms")
    print(f"  Agent Construct:{result.timing.agent_construction_ms:>10.2f} ms")
    print(f"  Total Run:      {result.timing.total_run_ms:>10.2f} ms")
    
    # Show top 5 functions
    print("\n🔥 Top 5 Functions by Cumulative Time:")
    for i, func in enumerate(result.top_functions[:5], 1):
        print(f"  {i}. {func.name}: {func.cumtime_ms:.2f}ms")
    
    # Show response preview
    print(f"\n💬 Response: {result.response[:100]}...")


if __name__ == "__main__":
    main()
