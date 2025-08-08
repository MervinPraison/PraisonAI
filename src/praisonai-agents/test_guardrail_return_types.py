#!/usr/bin/env python3
"""
Test different guardrail return types to ensure both GuardrailResult 
and Tuple[bool, Any] work correctly. This addresses issue #875.
"""

import sys
import os
from typing import Tuple, Any

from praisonaiagents import Agent, Task, TaskOutput, GuardrailResult
import inspect


def test_guardrail_return_types():
    """Test that both GuardrailResult and Tuple[bool, Any] return types are accepted."""
    print("Testing guardrail return type validation...")
    
    # Test 1: GuardrailResult return type
    def validate_with_guardrailresult(task_output: TaskOutput) -> GuardrailResult:
        """Validation function returning GuardrailResult."""
        if len(task_output.raw) < 10:
            return GuardrailResult(
                success=False,
                result=None,
                error="Output is too short"
            )
        return GuardrailResult(
            success=True,
            result=task_output,
            error=""
        )
    
    # Test 2: Tuple[bool, Any] return type
    def validate_with_tuple(task_output: TaskOutput) -> Tuple[bool, Any]:
        """Validation function returning tuple."""
        if len(task_output.raw) < 10:
            return False, "Output is too short"
        return True, task_output
    
    # Test 3: No return type annotation
    def validate_no_annotation(task_output: TaskOutput):
        """Validation function without return type annotation."""
        if len(task_output.raw) < 10:
            return False, "Output is too short"
        return True, task_output
    
    # Create test agent
    agent = Agent(
        name="Test Agent",
        role="Tester",
        goal="Test guardrails",
        backstory="Testing guardrail functionality",
        llm="gpt-5-nano"
    )
    
    # Test creating tasks with each guardrail type
    tests = [
        ("GuardrailResult return type", validate_with_guardrailresult),
        ("Tuple[bool, Any] return type", validate_with_tuple),
        ("No return type annotation", validate_no_annotation)
    ]
    
    for test_name, guardrail_func in tests:
        print(f"\nTesting {test_name}...")
        try:
            task = Task(
                description="Test task",
                expected_output="Test output",
                agent=agent,
                guardrail=guardrail_func
            )
            print(f"✓ Task created successfully with {test_name}")
            
            # Verify guardrail was set up
            assert task._guardrail_fn is not None, "Guardrail function not set"
            
            # Test guardrail processing
            test_output = TaskOutput(
                description="Test",
                raw="This is a test output that is long enough",
                agent="Test Agent"
            )
            
            result = task._process_guardrail(test_output)
            assert isinstance(result, GuardrailResult), f"Expected GuardrailResult, got {type(result)}"
            assert result.success, "Guardrail validation should pass"
            print(f"✓ Guardrail processing works with {test_name}")
            
        except Exception as e:
            print(f"✗ Failed with {test_name}: {e}")
            return False
    
    print("\n✓ All guardrail return type tests passed!")
    return True


def test_guardrail_result_handling():
    """Test that _process_guardrail correctly handles both return types."""
    print("\nTesting guardrail result handling...")
    
    # Create test agent and task
    agent = Agent(
        name="Test Agent",
        role="Tester",
        goal="Test guardrails",
        backstory="Testing guardrail functionality",
        llm="gpt-5-nano"
    )
    
    test_output = TaskOutput(
        description="Test",
        raw="Test output",
        agent="Test Agent"
    )
    
    # Test 1: Function returning GuardrailResult
    def return_guardrailresult(output: TaskOutput) -> GuardrailResult:
        return GuardrailResult(success=True, result=output, error="")
    
    task1 = Task(
        description="Test",
        agent=agent,
        guardrail=return_guardrailresult
    )
    
    result1 = task1._process_guardrail(test_output)
    assert isinstance(result1, GuardrailResult), "Should return GuardrailResult"
    assert result1.success, "Should be successful"
    print("✓ GuardrailResult return handled correctly")
    
    # Test 2: Function returning tuple
    def return_tuple(output: TaskOutput) -> Tuple[bool, Any]:
        return True, output
    
    task2 = Task(
        description="Test",
        agent=agent,
        guardrail=return_tuple
    )
    
    result2 = task2._process_guardrail(test_output)
    assert isinstance(result2, GuardrailResult), "Should convert tuple to GuardrailResult"
    assert result2.success, "Should be successful"
    print("✓ Tuple return converted correctly")
    
    print("✓ Guardrail result handling tests passed!")
    return True


if __name__ == "__main__":
    print("Running guardrail return type tests for issue #875...")
    
    success = True
    success &= test_guardrail_return_types()
    success &= test_guardrail_result_handling()
    
    if success:
        print("\n✅ All tests passed! The fix for issue #875 is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)