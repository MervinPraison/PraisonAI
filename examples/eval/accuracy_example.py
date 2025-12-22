"""
Accuracy Evaluation Example

This example demonstrates how to evaluate agent output accuracy
by comparing against expected outputs using LLM-as-judge.
"""

from praisonaiagents import Agent
from praisonaiagents.eval import AccuracyEvaluator

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

# You can also evaluate pre-generated outputs
output = "The answer is 4"
result2 = evaluator.evaluate_output(output, print_summary=True)
