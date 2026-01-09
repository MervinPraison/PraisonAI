"""
Performance Evaluation Example

This example demonstrates how to benchmark agent performance
by measuring runtime and memory usage across multiple iterations.
"""

import os
from praisonaiagents import Agent
from praisonaiagents.eval import PerformanceEvaluator

# Check if we have an API key
has_api_key = os.getenv("OPENAI_API_KEY") is not None

if has_api_key:
    print("--- Testing Agent Performance ---")
    # Create a simple agent
    agent = Agent(
        instructions="You are a helpful assistant. Answer questions briefly."
    )

    # Create performance evaluator
    evaluator = PerformanceEvaluator(
        agent=agent,
        input_text="What is the capital of France?",
        num_iterations=10,  # Run 10 benchmark iterations
        warmup_runs=2,      # 2 warmup runs before measurement
        track_memory=True,  # Track memory usage
        output="verbose"
    )

    # Run evaluation
    result = evaluator.run(print_summary=True)

    # Access detailed metrics
    print("\nAgent Performance Results:")
    print(f"  Average Time: {result.avg_run_time:.4f}s")
    print(f"  Min Time: {result.min_run_time:.4f}s")
    print(f"  Max Time: {result.max_run_time:.4f}s")
    print(f"  Median Time: {result.median_run_time:.4f}s")
    print(f"  P95 Time: {result.p95_run_time:.4f}s")
    print(f"  Avg Memory: {result.avg_memory:.2f} MB")
else:
    print("⚠️  No OPENAI_API_KEY found. Skipping agent performance test...")

# You can also benchmark any function
def my_function():
    import time
    time.sleep(0.1)
    return "done"

func_evaluator = PerformanceEvaluator(
    func=my_function,
    num_iterations=5,
    warmup_runs=1,
    track_memory=False
)

func_result = func_evaluator.run(print_summary=True)
