"""
Reliability Evaluation Example

This example demonstrates how to verify that agents call
the expected tools during execution.
"""

import os
from praisonaiagents import Agent
from praisonaiagents.eval import ReliabilityEvaluator


def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


def calculate(expression: str) -> str:
    """Calculate a math expression."""
    return str(eval(expression))


# Check if we have an API key
has_api_key = os.getenv("OPENAI_API_KEY") is not None

if has_api_key:
    print("--- Testing Agent Tool Call Reliability ---")
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
    print("\nAgent Reliability Results:")
    print(f"  Passed: {result.passed}")
    print(f"  Pass Rate: {result.pass_rate:.1%}")
else:
    print("⚠️  No OPENAI_API_KEY found. Skipping agent reliability test...")
    print("Agent would fail to call tools without API key (expected behavior)")

# You can also evaluate pre-recorded tool calls (doesn't need API key)
print("\n--- Testing Pre-recorded Tool Call Evaluation ---")
# Create a mock agent for tool call evaluation
mock_agent = Agent(instructions="Mock agent")
evaluator = ReliabilityEvaluator(
    agent=mock_agent,
    expected_tools=["search_web", "calculate"],  # Tools that should be called
    forbidden_tools=["delete_file"],  # Tools that should NOT be called
    verbose=True
)

result2 = evaluator.evaluate_tool_calls(
    actual_tools=["search_web", "calculate"],
    print_summary=True
)

print("\nPre-recorded Tool Call Results:")
print(f"  Passed: {result2.passed}")
print(f"  Pass Rate: {result2.pass_rate:.1%}")
