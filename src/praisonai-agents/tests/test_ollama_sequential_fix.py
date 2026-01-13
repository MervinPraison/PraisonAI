#!/usr/bin/env python3
"""
Test script to verify Ollama sequential tool calling argument mixing fix.

This test validates that the parameter validation and filtering fix correctly handles
the case where Ollama generates tool calls with mixed parameters from different functions.
"""

import logging
from praisonaiagents.llm.llm import LLM

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Test functions matching the issue description
def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers
    """
    return a * b

def test_ollama_argument_validation():
    """
    Test the Ollama argument validation and filtering functionality.
    """
    print("Testing Ollama argument validation and filtering...")
    
    llm = LLM(model="ollama/llama3.2")
    tools = [get_stock_price, multiply]
    
    # Test case 1: Valid arguments (should pass through unchanged)
    print("\n1. Testing valid arguments:")
    valid_args = {"a": 100, "b": 2}
    filtered_args = llm._validate_and_filter_ollama_arguments("multiply", valid_args, tools)
    print(f"Original: {valid_args}")
    print(f"Filtered: {filtered_args}")
    assert filtered_args == valid_args, "Valid arguments should pass through unchanged"
    print("✅ Valid arguments test passed")
    
    # Test case 2: Mixed arguments (the actual issue from #918)
    print("\n2. Testing mixed arguments (the main issue):")
    mixed_args = {"a": "get_stock_price", "company_name": "Google", "b": "2"}
    filtered_args = llm._validate_and_filter_ollama_arguments("multiply", mixed_args, tools)
    # Note: The method may coerce "2" to int 2 based on type hints - both are acceptable
    expected_filtered_str = {"a": "get_stock_price", "b": "2"}  # String version
    expected_filtered_int = {"a": "get_stock_price", "b": 2}    # Int version (coerced)
    print(f"Original: {mixed_args}")
    print(f"Filtered: {filtered_args}")
    print(f"Expected: {expected_filtered_str} or {expected_filtered_int}")
    assert filtered_args == expected_filtered_str or filtered_args == expected_filtered_int, \
        f"Expected {expected_filtered_str} or {expected_filtered_int}, got {filtered_args}"
    print("✅ Mixed arguments filtering test passed")
    
    # Test case 3: All invalid arguments
    print("\n3. Testing all invalid arguments:")
    invalid_args = {"invalid_param1": "value1", "invalid_param2": "value2"}
    filtered_args = llm._validate_and_filter_ollama_arguments("multiply", invalid_args, tools)
    expected_empty = {}
    print(f"Original: {invalid_args}")
    print(f"Filtered: {filtered_args}")
    assert filtered_args == expected_empty, "All invalid arguments should be filtered out"
    print("✅ Invalid arguments filtering test passed")
    
    # Test case 4: Function not found in tools
    print("\n4. Testing function not found:")
    some_args = {"param": "value"}
    filtered_args = llm._validate_and_filter_ollama_arguments("nonexistent_function", some_args, tools)
    print(f"Original: {some_args}")
    print(f"Filtered: {filtered_args}")
    assert filtered_args == some_args, "Arguments should pass through if function not found"
    print("✅ Function not found test passed")
    
    # Test case 5: Empty tools list
    print("\n5. Testing empty tools list:")
    some_args = {"param": "value"}
    filtered_args = llm._validate_and_filter_ollama_arguments("multiply", some_args, [])
    print(f"Original: {some_args}")
    print(f"Filtered: {filtered_args}")
    assert filtered_args == some_args, "Arguments should pass through if no tools provided"
    print("✅ Empty tools test passed")
    
    print("\n🎉 All Ollama argument validation tests passed!")
    return True

def test_provider_detection():
    """
    Test the Ollama provider detection functionality.
    """
    print("\nTesting Ollama provider detection...")
    
    # Test Ollama provider detection
    ollama_llm = LLM(model="ollama/llama3.2")
    assert ollama_llm._is_ollama_provider(), "Should detect ollama/ prefix"
    print("✅ Ollama prefix detection works")
    
    # Test non-Ollama provider
    openai_llm = LLM(model="gpt-4o-mini")
    assert not openai_llm._is_ollama_provider(), "Should not detect OpenAI as Ollama"
    print("✅ Non-Ollama provider detection works")
    
    print("✅ Provider detection tests passed!")
    return True

if __name__ == "__main__":
    print("Running Ollama sequential tool calling fix tests...")
    print("=" * 60)
    
    # Run tests
    try:
        test_provider_detection()
        test_ollama_argument_validation()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("The Ollama sequential tool calling argument mixing issue has been fixed!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()