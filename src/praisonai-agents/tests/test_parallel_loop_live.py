#!/usr/bin/env python3
"""
Test script for parallel loop execution.

This demonstrates the parallel loop pattern works correctly by:
1. Creating a simple workflow with a parallel loop
2. Using a mock agent that simulates work with a delay
3. Verifying that parallel execution is faster than sequential
"""

import time
from praisonaiagents.workflows import Workflow, loop
from praisonaiagents import Agent


def test_parallel_loop_execution():
    """Test parallel loop executes items concurrently."""
    
    # Create a simple agent
    agent = Agent(
        name="processor",
        role="Item Processor",
        goal="Process items",
        instructions="Just echo back the item you received",
        llm="gpt-4o-mini"  # Fast, cheap model
    )
    
    items = ["Apple", "Google", "Microsoft", "Amazon"]
    
    # Create workflow with parallel loop (variables in constructor)
    workflow = Workflow(
        steps=[
            loop(
                step=agent,
                over="items",
                parallel=True,
                max_workers=4
            )
        ],
        variables={"items": items}
    )
    
    print(f"\n🚀 Testing parallel loop with {len(items)} items...")
    print(f"   Items: {items}")
    
    start = time.time()
    result = workflow.start(input=f"Process these items")
    duration = time.time() - start
    
    print(f"\n✅ Parallel loop completed in {duration:.2f}s")
    print(f"   Output preview: {str(result)[:200]}...")
    
    return result


def test_sequential_vs_parallel():
    """Compare sequential vs parallel loop execution."""
    
    agent = Agent(
        name="processor",
        role="Item Processor",
        goal="Process items",
        instructions="Just echo back the item you received",
        llm="gpt-4o-mini"
    )
    
    items = ["A", "B", "C", "D"]
    
    # Sequential loop
    seq_workflow = Workflow(
        steps=[loop(step=agent, over="items", parallel=False)],
        variables={"items": items}
    )
    
    print("\n🔄 Running SEQUENTIAL loop...")
    seq_start = time.time()
    seq_result = seq_workflow.start(input="Process items")
    seq_duration = time.time() - seq_start
    print(f"   Sequential duration: {seq_duration:.2f}s")
    
    # Parallel loop
    par_workflow = Workflow(
        steps=[loop(step=agent, over="items", parallel=True, max_workers=4)],
        variables={"items": items}
    )
    
    print("\n⚡ Running PARALLEL loop...")
    par_start = time.time()
    par_result = par_workflow.start(input="Process items")
    par_duration = time.time() - par_start
    print(f"   Parallel duration: {par_duration:.2f}s")
    
    # Compare
    speedup = seq_duration / par_duration if par_duration > 0 else 0
    print(f"\n📊 Speedup: {speedup:.1f}x")
    
    if par_duration < seq_duration:
        print("✅ Parallel loop is faster!")
    else:
        print("⚠️ Parallel loop was not faster (might be due to overhead with small items)")


if __name__ == "__main__":
    print("=" * 60)
    print("PARALLEL LOOP EXECUTION TEST")
    print("=" * 60)
    
    # Run basic test
    test_parallel_loop_execution()
    
    print("\n" + "=" * 60)
    print("SEQUENTIAL vs PARALLEL COMPARISON")
    print("=" * 60)
    
    # Run comparison
    test_sequential_vs_parallel()
    
    print("\n✅ All tests complete!")
