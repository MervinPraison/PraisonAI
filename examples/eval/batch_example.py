"""
Batch Evaluation Example

This example demonstrates how to run batch evaluations
from a JSON test file.
"""

import os
import json
import tempfile
from praisonaiagents.eval import AccuracyEvaluator

# Check if we have an API key
has_api_key = os.getenv("OPENAI_API_KEY") is not None

# Create a test file with multiple test cases
test_cases = [
    {
        "input": "What is 2 + 2?",
        "expected": "4"
    },
    {
        "input": "What is the capital of France?",
        "expected": "Paris"
    },
    {
        "input": "What color is the sky?",
        "expected": "Blue"
    }
]

# Save test cases to a temporary file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(test_cases, f)
    test_file = f.name

print(f"Test file created: {test_file}")
print(f"Running {len(test_cases)} test cases...")

if has_api_key:
    # You can use the CLI for batch evaluation:
    # praisonai eval batch --agent agents.yaml --test-file tests.json --batch-type accuracy

    # Or programmatically:
    from praisonaiagents import Agent

    agent = Agent(
        instructions="You are a helpful assistant. Answer questions concisely."
    )

    results = []
    for i, test_case in enumerate(test_cases):
        print(f"\nTest {i + 1}: {test_case['input']}")
        
        evaluator = AccuracyEvaluator(
            agent=agent,
            input_text=test_case["input"],
            expected_output=test_case["expected"],
            num_iterations=1
        )
        
        result = evaluator.run()
        results.append({
            "input": test_case["input"],
            "expected": test_case["expected"],
            "score": result.avg_score,
            "passed": result.passed
        })
        
        print(f"  Score: {result.avg_score}/10")
        print(f"  Passed: {result.passed}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*50}")
    print(f"Summary: {passed}/{len(results)} tests passed")
    print(f"Pass Rate: {passed/len(results):.1%}")
else:
    print("⚠️  No OPENAI_API_KEY found. Running mock batch evaluation...")
    
    # Mock evaluation without API key
    results = []
    for i, test_case in enumerate(test_cases):
        print(f"\nTest {i + 1}: {test_case['input']}")
        
        # Mock result (all would fail without API key)
        mock_score = 0.0
        mock_passed = False
        
        results.append({
            "input": test_case["input"],
            "expected": test_case["expected"],
            "score": mock_score,
            "passed": mock_passed
        })
        
        print(f"  Score: {mock_score}/10 (mock)")
        print(f"  Passed: {mock_passed} (expected without API key)")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*50}")
    print(f"Summary: {passed}/{len(results)} tests passed (mock evaluation)")
    print(f"Pass Rate: {passed/len(results):.1%}")
    print("\nTo run real batch evaluation, set OPENAI_API_KEY environment variable")
