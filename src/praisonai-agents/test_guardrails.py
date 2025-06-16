#!/usr/bin/env python3
"""
Test script for guardrails functionality in PraisonAI Agents.
"""

import os
import sys
import logging

from praisonaiagents import Agent, Task, TaskOutput
from praisonaiagents.guardrails import GuardrailResult, LLMGuardrail
from typing import Tuple, Any


def test_function_guardrail():
    """Test function-based guardrail."""
    print("Testing function-based guardrail...")
    
    def validate_output(task_output: TaskOutput) -> Tuple[bool, Any]:
        """Simple validation function."""
        if "error" in task_output.raw.lower():
            return False, "Output contains errors"
        if len(task_output.raw) < 10:
            return False, "Output is too short"
        return True, task_output
    
    # Create agent and task with guardrail
    agent = Agent(
        name="Test Agent",
        role="Tester", 
        goal="Test guardrails",
        backstory="I am testing the guardrail functionality"
    )
    
    task = Task(
        description="Write a simple hello message",
        expected_output="A friendly greeting message",
        agent=agent,
        guardrail=validate_output,
        max_retries=2
    )
    
    # Test with good output
    good_output = TaskOutput(
        description="Test task",
        raw="Hello! This is a friendly greeting message from the agent.",
        agent="Test Agent"
    )
    
    result = task._process_guardrail(good_output)
    assert result.success, f"Good output should pass: {result.error}"
    print("✓ Good output passed guardrail")
    
    # Test with bad output
    bad_output = TaskOutput(
        description="Test task", 
        raw="Error occurred",
        agent="Test Agent"
    )
    
    result = task._process_guardrail(bad_output)
    assert not result.success, "Bad output should fail guardrail"
    print("✓ Bad output failed guardrail as expected")
    
    print("Function-based guardrail test passed!\n")


def test_string_guardrail():
    """Test string-based LLM guardrail."""
    print("Testing string-based LLM guardrail...")
    
    # Mock LLM for testing
    class MockLLM:
        def chat(self, prompt, **kwargs):
            # Extract the actual output to validate from the prompt
            # The LLMGuardrail sends a structured prompt with "Output to Validate:" section
            if "Output to Validate:" in prompt:
                # Split by "Output to Validate:" and get the content after it
                parts = prompt.split("Output to Validate:")
                if len(parts) > 1:
                    output_content = parts[1].strip()
                    # Check only the output content, not the validation criteria
                    if "error" in output_content.lower():
                        return "FAIL: The output contains error messages"
                    return "PASS"
            
            # Fallback: if no "Output to Validate:" section, check the prompt directly
            # This should rarely happen with proper LLMGuardrail usage
            if "error" in prompt.lower() and "check if" not in prompt.lower():
                return "FAIL: The output contains error messages"
            return "PASS"
    
    # Create agent with mock LLM
    agent = Agent(
        name="Test Agent",
        role="Tester",
        goal="Test guardrails", 
        backstory="I am testing the guardrail functionality"
    )
    agent.llm = MockLLM()
    
    task = Task(
        description="Write a simple hello message",
        expected_output="A friendly greeting message",
        agent=agent,
        guardrail="Check if the output is professional and does not contain errors",
        max_retries=2
    )
    
    # Test with good output
    good_output = TaskOutput(
        description="Test task",
        raw="Hello! This is a professional greeting message.",
        agent="Test Agent"
    )
    
    result = task._process_guardrail(good_output)
    assert result.success, f"Good output should pass: {result.error}"
    print("✓ Good output passed LLM guardrail")
    
    # Test with bad output  
    bad_output = TaskOutput(
        description="Test task",
        raw="There was an error in the system",
        agent="Test Agent"
    )
    
    result = task._process_guardrail(bad_output)
    assert not result.success, "Bad output should fail LLM guardrail"
    print("✓ Bad output failed LLM guardrail as expected")
    
    print("String-based LLM guardrail test passed!\n")


def test_guardrail_result():
    """Test GuardrailResult helper methods."""
    print("Testing GuardrailResult...")
    
    # Test success case
    success_result = GuardrailResult.from_tuple((True, "Modified output"))
    assert success_result.success
    assert success_result.result == "Modified output"
    assert success_result.error == ""
    print("✓ Success result created correctly")
    
    # Test failure case
    failure_result = GuardrailResult.from_tuple((False, "Validation failed"))
    assert not failure_result.success
    assert failure_result.result is None
    assert failure_result.error == "Validation failed"
    print("✓ Failure result created correctly")
    
    print("GuardrailResult test passed!\n")


def main():
    """Run all tests."""
    print("Running PraisonAI Agents Guardrails Tests...\n")
    
    try:
        test_guardrail_result()
        test_function_guardrail()
        test_string_guardrail()
        
        print("🎉 All guardrail tests passed!")
        print("\nGuardrails implementation is working correctly!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(level=logging.WARNING)
    
    success = main()
    sys.exit(0 if success else 1)