"""
Criteria Evaluation Example

This example demonstrates how to evaluate agent outputs
against custom criteria using LLM-as-judge.
"""

from praisonaiagents import Agent
from praisonaiagents.eval import CriteriaEvaluator

# Create a customer service agent
agent = Agent(
    instructions="You are a friendly customer service agent. Be helpful and empathetic."
)

# Create criteria evaluator with numeric scoring
evaluator = CriteriaEvaluator(
    criteria="Response is helpful, empathetic, and provides a clear solution",
    agent=agent,
    input_text="I'm frustrated because my order hasn't arrived yet.",
    scoring_type="numeric",  # Score 1-10
    threshold=7.0,           # Pass if score >= 7
    num_iterations=2,
    verbose=True
)

# Run evaluation
result = evaluator.run(print_summary=True)

print(f"\nAverage Score: {result.avg_score}/10")
print(f"Pass Rate: {result.pass_rate:.1%}")
print(f"Passed: {result.passed}")

# Binary scoring example (pass/fail)
binary_evaluator = CriteriaEvaluator(
    criteria="Response does not contain any offensive language",
    agent=agent,
    input_text="Tell me a joke",
    scoring_type="binary",  # Pass or Fail
    verbose=True
)

binary_result = binary_evaluator.run(print_summary=True)

# Evaluate pre-generated output
output = "I understand your frustration. Let me check on your order right away."
result2 = evaluator.evaluate_output(output, print_summary=True)

# With on_fail callback
def handle_failure(score):
    print(f"ALERT: Evaluation failed with score {score.score}")
    print(f"Reasoning: {score.reasoning}")

callback_evaluator = CriteriaEvaluator(
    criteria="Response is professional and helpful",
    agent=agent,
    input_text="Help me",
    on_fail=handle_failure,
    threshold=8.0
)

callback_evaluator.run()
