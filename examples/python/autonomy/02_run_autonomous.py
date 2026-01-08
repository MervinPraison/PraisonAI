"""
run_autonomous() Example.

Demonstrates the unified autonomous loop with real API calls.

Run with: python 02_run_autonomous.py

Requirements:
- OPENAI_API_KEY environment variable set
"""

from praisonaiagents import Agent


def main():
    print("=" * 60)
    print("run_autonomous() Example")
    print("=" * 60)
    
    # Create agent with autonomy
    agent = Agent(
        instructions="You are a helpful assistant. When asked a question, provide a clear answer and say 'Task completed' at the end.",
        autonomy={"max_iterations": 5},
    )
    
    # Test 1: Simple task (should complete in 1 iteration)
    print("\n1. Simple Task (direct stage):")
    result = agent.run_autonomous(
        "What is the capital of France? Say 'Task completed' after answering.",
        max_iterations=3,
    )
    
    print(f"   Success: {result.success}")
    print(f"   Completion reason: {result.completion_reason}")
    print(f"   Iterations: {result.iterations}")
    print(f"   Stage: {result.stage}")
    print(f"   Duration: {result.duration_seconds:.2f}s")
    print(f"   Output: {result.output[:100]}...")
    
    # Test 2: Check result attributes
    print("\n2. Result Attributes:")
    print(f"   Has actions: {len(result.actions) > 0}")
    print(f"   Has error: {result.error is not None}")
    
    print("\n" + "=" * 60)
    print("✓ run_autonomous() example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
