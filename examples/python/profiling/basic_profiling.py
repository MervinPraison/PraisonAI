"""
Basic Profiling Example for PraisonAI

This example demonstrates how to use the unified profiler programmatically
to measure agent performance.

Run with:
    python basic_profiling.py
"""

import os

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

from praisonai.cli.execution import (
    ExecutionRequest,
    Profiler,
    ProfilerConfig,
)


def main():
    """Run a profiled query and display results."""
    
    # Configure profiler (Layer 1 = basic profiling with function stats)
    config = ProfilerConfig(
        layer=1,             # 0=minimal, 1=basic, 2=deep
        limit=15,            # Show top 15 functions
        show_callers=False,  # Set True for caller info (layer 2)
        show_callees=False,  # Set True for callee info (layer 2)
    )
    
    # Create execution request
    request = ExecutionRequest(
        prompt="What is 2+2?",
        agent_name="ProfiledAgent",
    )
    
    # Run profiled query
    print("🔬 Running profiled query...")
    profiler = Profiler(config)
    result, report = profiler.profile_sync(request)
    
    # Print formatted report
    print("\n" + report.to_text())
    
    # Access timing data programmatically
    print("\n📊 Timing Summary:")
    print(f"  Imports:        {report.timing.imports_ms:>10.2f} ms")
    print(f"  Agent Init:     {report.timing.agent_init_ms:>10.2f} ms")
    print(f"  Execution:      {report.timing.execution_ms:>10.2f} ms")
    print(f"  Total:          {report.timing.total_ms:>10.2f} ms")
    
    # Show top 5 functions
    if report.functions:
        print("\n🔥 Top 5 Functions by Cumulative Time:")
        for i, func in enumerate(report.functions[:5], 1):
            print(f"  {i}. {func.name}: {func.cumulative_time_ms:.2f}ms")
    
    # Show response
    print(f"\n💬 Response: {result.output}")
    
    # Export to JSON
    print("\n📄 JSON Export available via: report.to_json()")


if __name__ == "__main__":
    main()
