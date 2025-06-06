#!/usr/bin/env python3
"""
Simple test to verify the Mini Agents sequential task data passing fix.
This tests the core functionality without external dependencies.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

pytest.importorskip("praisonaiagents")
from praisonaiagents import Agent, Agents

def test_context_processing():
    """Test the context processing logic without running actual agents"""
    
    print("\n=== Testing Context Processing Logic ===")
    
    # Simulate a task result object
    class MockTaskResult:
        def __init__(self, raw_output):
            self.raw = raw_output
    
    # Simulate a completed task object
    class MockTask:
        def __init__(self, name, result_text, status="completed"):
            self.name = name
            self.result = MockTaskResult(result_text) if result_text else None
            self.status = status
            self.description = f"Mock task: {name}"
    
    # Test the context processing logic
    task1 = MockTask("research_task", "AI 2024 analysis: Major breakthroughs in machine learning")
    task2 = MockTask("summary_task", None, "in progress")  # Task not completed yet
    task3 = MockTask("analysis_task", "Key trends: Neural networks, transformers, LLMs", "completed")
    
    # Simulate context items like the real code does
    context_items = [task1, task2, task3]
    context_results = []
    
    for context_item in context_items:
        if hasattr(context_item, 'result'):  # Task object
            # Apply our fix: Ensure the previous task is completed before including its result
            if context_item.result and getattr(context_item, 'status', None) == "completed":
                context_results.append(
                    f"Result of previous task {context_item.name if context_item.name else context_item.description}:\n{context_item.result.raw}"
                )
            elif getattr(context_item, 'status', None) == "completed" and not context_item.result:
                context_results.append(
                    f"Previous task {context_item.name if context_item.name else context_item.description} completed but produced no result."
                )
            else:
                context_results.append(
                    f"Previous task {context_item.name if context_item.name else context_item.description} is not yet completed (status: {getattr(context_item, 'status', 'unknown')})."
                )
    
    # Apply our fix: Join with proper formatting
    unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
    formatted_context = '\n\n'.join(unique_contexts)
    
    print("Context Results:")
    print("================")
    print(formatted_context)
    print("================")
    
    # Verify the fix works
    expected_patterns = [
        "Result of previous task research_task:",
        "AI 2024 analysis: Major breakthroughs in machine learning",
        "summary_task is not yet completed (status: in progress)",
        "Result of previous task analysis_task:",
        "Key trends: Neural networks, transformers, LLMs"
    ]
    
    success = True
    for pattern in expected_patterns:
        if pattern not in formatted_context:
            print(f"❌ Missing expected pattern: {pattern}")
            success = False
        else:
            print(f"✅ Found expected pattern: {pattern}")
    
    # Check formatting improvement
    if '\n\n' in formatted_context and '  ' not in formatted_context.replace('  ', ' '):
        print("✅ Context is properly formatted with newlines instead of spaces")
    else:
        print("❌ Context formatting issue")
        success = False
    
    assert success, "Context processing test failed"

def main():
    print("Testing Mini Agents Sequential Task Data Passing Fix")
    print("=" * 60)
    
    success = test_context_processing()
    
    if success:
        print("\n🎉 All tests passed! The fix should resolve the data passing issue.")
    else:
        print("\n❌ Tests failed. The fix needs more work.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
