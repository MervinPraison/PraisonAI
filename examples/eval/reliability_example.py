"""
Reliability Evaluation Example

This example demonstrates how to verify that agents call
the expected tools during execution.
"""

from praisonaiagents import Agent
from praisonaiagents.eval import ReliabilityEvaluator


def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


def calculate(expression: str) -> str:
    """Calculate a math expression."""
    return str(eval(expression))


# Create an agent with tools
agent = Agent(
    instructions="You are a helpful assistant with access to search and calculator tools.",
    tools=[search_web, calculate]
)

# Create reliability evaluator
evaluator = ReliabilityEvaluator(
    agent=agent,
    input_text="Search for the weather in Paris and calculate 25 * 4",
    expected_tools=["search_web", "calculate"],  # Tools that should be called
    forbidden_tools=["delete_file"],  # Tools that should NOT be called
    verbose=True
)

# Run evaluation
result = evaluator.run(print_summary=True)

# Check results
print(f"\nPassed: {result.passed}")
print(f"Pass Rate: {result.pass_rate:.1%}")

# You can also evaluate pre-recorded tool calls
result2 = evaluator.evaluate_tool_calls(
    actual_tools=["search_web", "calculate"],
    print_summary=True
)
