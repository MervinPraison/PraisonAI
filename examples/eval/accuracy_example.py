"""
Accuracy Evaluation Example

This example demonstrates how to evaluate agent output accuracy
by comparing against expected outputs using LLM-as-judge.
"""

import os
from praisonaiagents import Agent
from praisonaiagents.eval import AccuracyEvaluator

# Check if we have an API key
has_api_key = os.getenv("OPENAI_API_KEY") is not None

if has_api_key:
    # Create a simple math tutor agent
    agent = Agent(
        instructions="You are a math tutor. Answer math questions concisely with just the number."
    )

    # Create accuracy evaluator
    evaluator = AccuracyEvaluator(
        agent=agent,
        input_text="What is 2 + 2?",
        expected_output="4",
        num_iterations=3,  # Run 3 times for statistical significance
        verbose=True
    )

    # Run evaluation
    result = evaluator.run(print_summary=True)

    # Check results
    print(f"\nAverage Score: {result.avg_score}/10")
    print(f"Passed: {result.passed}")
else:
    print("⚠️  No OPENAI_API_KEY found. Using mock evaluation...")
    
    # Create evaluator without agent for mock testing
    evaluator = AccuracyEvaluator(
        func=lambda x: "4",  # Mock function
        input_text="What is 2 + 2?",
        expected_output="4",
        num_iterations=1,
        verbose=True
    )
    
    # Test with mock output
    try:
        result = evaluator.run(print_summary=True)
        print(f"\nMock Average Score: {result.avg_score}/10")
        print(f"Mock Passed: {result.passed}")
    except Exception as e:
        print(f"Mock evaluation failed: {e}")
        print("This is expected without an API key")

# You can also evaluate pre-generated outputs
print("\n--- Testing pre-generated output evaluation ---")
output = "The answer is 4"

if has_api_key:
    try:
        result2 = evaluator.evaluate_output(output, print_summary=True)
        print(f"Pre-generated output score: {result2.avg_score}/10")
    except Exception as e:
        print(f"Pre-generated evaluation failed: {e}")
else:
    print("⚠️  Skipping pre-generated evaluation (no API key)")
    print("To run full evaluation, set OPENAI_API_KEY environment variable")
