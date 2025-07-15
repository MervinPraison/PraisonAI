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
    expected_filtered = {"a": "get_stock_price", "b": "2"}  # Should remove 'company_name'
    print(f"Original: {mixed_args}")
    print(f"Filtered: {filtered_args}")
    print(f"Expected: {expected_filtered}")
    assert filtered_args == expected_filtered, f"Expected {expected_filtered}, got {filtered_args}"
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
    
    # Test case 6: Pre-formatted OpenAI tool dictionaries
    print("\n6. Testing pre-formatted OpenAI tool dictionaries:")
    openai_tools = [
        {
            'type': 'function',
            'function': {
                'name': 'get_stock_price',
                'description': 'Get the stock price of a company',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'company_name': {'type': 'string', 'description': 'Company name'}
                    },
                    'required': ['company_name']
                }
            }
        },
        {
            'type': 'function', 
            'function': {
                'name': 'multiply',
                'description': 'Multiply two numbers',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'a': {'type': 'integer', 'description': 'First number'},
                        'b': {'type': 'integer', 'description': 'Second number'}
                    },
                    'required': ['a', 'b']
                }
            }
        }
    ]
    
    # Test mixed arguments with pre-formatted tools (should allow all arguments since we can't validate)
    mixed_args = {"a": "get_stock_price", "company_name": "Google", "b": "2"}
    filtered_args = llm._validate_and_filter_ollama_arguments("multiply", mixed_args, openai_tools)
    print(f"Original: {mixed_args}")
    print(f"Filtered: {filtered_args}")
    print("Note: Pre-formatted tools cannot be validated, so arguments pass through")
    # For pre-formatted tools, we expect arguments to pass through unchanged due to graceful degradation
    assert filtered_args == mixed_args, f"Expected {mixed_args}, got {filtered_args}"
    print("✅ Pre-formatted OpenAI tool dictionaries test passed")

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

def test_helper_methods():
    """
    Test the new helper methods for tool name extraction and signature handling.
    """
    print("\nTesting helper methods...")
    
    llm = LLM(model="ollama/llama3.2")
    
    # Test _get_tool_name with callable function
    def test_func():
        pass
    
    assert llm._get_tool_name(test_func) == "test_func", "Should extract function name"
    print("✅ Function name extraction works")
    
    # Test _get_tool_name with OpenAI tool dictionary
    openai_tool = {
        'type': 'function',
        'function': {
            'name': 'test_tool',
            'description': 'Test tool'
        }
    }
    
    assert llm._get_tool_name(openai_tool) == "test_tool", "Should extract tool name from dictionary"
    print("✅ OpenAI tool name extraction works")
    
    # Test _get_tool_signature with callable function
    signature = llm._get_tool_signature(test_func)
    assert signature is not None, "Should return signature for callable function"
    print("✅ Function signature extraction works")
    
    # Test _get_tool_signature with OpenAI tool dictionary
    signature = llm._get_tool_signature(openai_tool)
    assert signature is None, "Should return None for OpenAI tool dictionaries"
    print("✅ OpenAI tool signature handling works (graceful degradation)")
    
    print("✅ Helper methods tests passed!")
    return True

if __name__ == "__main__":
    print("Running Ollama sequential tool calling fix tests...")
    print("=" * 60)
    
    # Run tests
    try:
        test_provider_detection()
        test_helper_methods() 
        test_ollama_argument_validation()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("The Ollama sequential tool calling argument mixing issue has been fixed!")
        print("✅ Supports both callable functions and pre-formatted OpenAI tool dictionaries")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()