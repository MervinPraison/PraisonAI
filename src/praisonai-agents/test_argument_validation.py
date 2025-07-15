#!/usr/bin/env python3
"""
Test script to validate the Ollama argument filtering logic.
"""

import sys
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from praisonaiagents.llm.llm import LLM

def get_stock_price(company_name: str) -> str:
    """Get the stock price of a company"""
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

def test_argument_validation():
    """Test the _validate_and_filter_ollama_arguments method."""
    
    llm = LLM(model="ollama/llama3.2")
    
    # Test case 1: Valid arguments for multiply
    print("=" * 60)
    print("Test 1: Valid arguments for multiply")
    print("=" * 60)
    
    valid_args = {"a": 100, "b": 2}
    result = llm._validate_and_filter_ollama_arguments("multiply", valid_args, [get_stock_price, multiply])
    print(f"Input: {valid_args}")
    print(f"Output: {result}")
    print(f"Test 1 PASSED: {result == valid_args}")
    
    # Test case 2: Invalid arguments for multiply (the issue case)
    print("\n" + "=" * 60)
    print("Test 2: Invalid arguments for multiply (mixing parameters)")
    print("=" * 60)
    
    invalid_args = {"a": "get_stock_price", "company_name": "Google", "b": "2"}
    result = llm._validate_and_filter_ollama_arguments("multiply", invalid_args, [get_stock_price, multiply])
    print(f"Input: {invalid_args}")
    print(f"Output: {result}")
    expected = {"a": "get_stock_price", "b": "2"}  # Should filter out company_name
    print(f"Expected: {expected}")
    print(f"Test 2 PASSED: {result == expected}")
    
    # Test case 3: Valid arguments for get_stock_price
    print("\n" + "=" * 60)
    print("Test 3: Valid arguments for get_stock_price")
    print("=" * 60)
    
    valid_stock_args = {"company_name": "Google"}
    result = llm._validate_and_filter_ollama_arguments("get_stock_price", valid_stock_args, [get_stock_price, multiply])
    print(f"Input: {valid_stock_args}")
    print(f"Output: {result}")
    print(f"Test 3 PASSED: {result == valid_stock_args}")
    
    # Test case 4: Invalid arguments for get_stock_price
    print("\n" + "=" * 60)
    print("Test 4: Invalid arguments for get_stock_price (extra parameters)")
    print("=" * 60)
    
    invalid_stock_args = {"company_name": "Google", "a": 100, "b": 2}
    result = llm._validate_and_filter_ollama_arguments("get_stock_price", invalid_stock_args, [get_stock_price, multiply])
    print(f"Input: {invalid_stock_args}")
    print(f"Output: {result}")
    expected_stock = {"company_name": "Google"}
    print(f"Expected: {expected_stock}")
    print(f"Test 4 PASSED: {result == expected_stock}")
    
    # Test case 5: Tool call parsing
    print("\n" + "=" * 60)
    print("Test 5: Tool call parsing with invalid arguments")
    print("=" * 60)
    
    # Simulate the problematic tool call
    tool_call = {
        "function": {
            "name": "multiply",
            "arguments": '{"a": "get_stock_price", "company_name": "Google", "b": "2"}'
        },
        "id": "tool_123"
    }
    
    function_name, arguments, tool_call_id = llm._parse_tool_call_arguments(tool_call, is_ollama=True, available_tools=[get_stock_price, multiply])
    print(f"Function: {function_name}")
    print(f"Arguments: {arguments}")
    print(f"Tool Call ID: {tool_call_id}")
    expected_filtered = {"a": "get_stock_price", "b": "2"}
    print(f"Expected Arguments: {expected_filtered}")
    print(f"Test 5 PASSED: {arguments == expected_filtered}")

if __name__ == "__main__":
    print("Testing Ollama argument validation logic...")
    test_argument_validation()
    print("\nAll tests completed!")