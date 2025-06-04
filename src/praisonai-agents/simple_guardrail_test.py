#!/usr/bin/env python3
"""
Simple test for guardrails functionality without full dependencies.
"""

import sys
import os
from typing import Tuple, Any

# Import only what we need for testing
from praisonaiagents.guardrails import GuardrailResult, LLMGuardrail
from praisonaiagents.main import TaskOutput


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


def test_function_guardrail():
    """Test function-based guardrail logic."""
    print("Testing function-based guardrail logic...")
    
    def validate_output(task_output: TaskOutput) -> Tuple[bool, Any]:
        """Simple validation function."""
        if "error" in task_output.raw.lower():
            return False, "Output contains errors"
        if len(task_output.raw) < 10:
            return False, "Output is too short"
        return True, task_output
    
    # Test with good output
    good_output = TaskOutput(
        description="Test task",
        raw="Hello! This is a friendly greeting message from the agent.",
        agent="Test Agent"
    )
    
    result = validate_output(good_output)
    guardrail_result = GuardrailResult.from_tuple(result)
    assert guardrail_result.success, f"Good output should pass: {guardrail_result.error}"
    print("✓ Good output passed function guardrail")
    
    # Test with bad output
    bad_output = TaskOutput(
        description="Test task", 
        raw="Error occurred",
        agent="Test Agent"
    )
    
    result = validate_output(bad_output)
    guardrail_result = GuardrailResult.from_tuple(result)
    assert not guardrail_result.success, "Bad output should fail guardrail"
    print("✓ Bad output failed function guardrail as expected")
    
    print("Function-based guardrail logic test passed!\n")


def test_llm_guardrail():
    """Test LLM guardrail logic."""
    print("Testing LLM guardrail logic...")
    
    # Mock LLM for testing that correctly parses the validation prompt
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
            
            # Fallback: if no "Output to Validate:" section, return pass
            return "PASS"
    
    # Create LLM guardrail
    mock_llm = MockLLM()
    llm_guardrail = LLMGuardrail(
        description="Check if the output is professional and does not contain errors",
        llm=mock_llm
    )
    
    # Test with good output
    good_output = TaskOutput(
        description="Test task",
        raw="Hello! This is a professional greeting message.",
        agent="Test Agent"
    )
    
    result = llm_guardrail(good_output)
    guardrail_result = GuardrailResult.from_tuple(result)
    assert guardrail_result.success, f"Good output should pass: {guardrail_result.error}"
    print("✓ Good output passed LLM guardrail")
    
    # Test with bad output  
    bad_output = TaskOutput(
        description="Test task",
        raw="There was an error in the system",
        agent="Test Agent"
    )
    
    result = llm_guardrail(bad_output)
    guardrail_result = GuardrailResult.from_tuple(result)
    assert not guardrail_result.success, "Bad output should fail LLM guardrail"
    print("✓ Bad output failed LLM guardrail as expected")
    
    print("LLM guardrail logic test passed!\n")


def main():
    """Run all tests."""
    print("Running Simple Guardrails Tests...\n")
    
    try:
        test_guardrail_result()
        test_function_guardrail()
        test_llm_guardrail()
        
        print("🎉 All simple guardrail tests passed!")
        print("\nGuardrails core logic is working correctly!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)