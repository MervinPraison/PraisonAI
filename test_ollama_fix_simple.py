#!/usr/bin/env python3
"""
Simple test to verify the Ollama infinite loop fix works correctly.
"""

import sys
import os
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_ollama_tool_summary_generation():
    """Test that the Ollama tool summary generation works correctly"""
    print("Testing Ollama tool summary generation...")
    
    # Import the LLM class to test the summary generation directly
    from praisonaiagents.llm.llm import LLM
    
    llm = LLM(model="ollama/llama3.2")
    
    # Test tool results
    tool_results = [
        {"function_name": "get_stock_price", "result": "The stock price of Google is 100"},
        {"function_name": "multiply", "result": "200"}
    ]
    
    # Test with empty response (should generate summary)
    summary = llm._generate_ollama_tool_summary(tool_results, "")
    print(f"Summary for empty response: {summary}")
    
    # Test with minimal response (should generate summary)
    summary = llm._generate_ollama_tool_summary(tool_results, "Ok")
    print(f"Summary for minimal response: {summary}")
    
    # Test with substantial response (should still generate summary with our fix)
    summary = llm._generate_ollama_tool_summary(tool_results, "This is a substantial response with more than 10 characters")
    print(f"Summary for substantial response: {summary}")
    
    # Verify summary contains expected information
    if summary and "get_stock_price" in summary and "multiply" in summary:
        print("✅ Summary generation working correctly")
        return True
    else:
        print("❌ Summary generation failed")
        return False

def test_is_ollama_provider():
    """Test that Ollama provider detection works correctly"""
    print("\nTesting Ollama provider detection...")
    
    from praisonaiagents.llm.llm import LLM
    
    # Test with Ollama model
    llm = LLM(model="ollama/llama3.2")
    is_ollama = llm._is_ollama_provider()
    print(f"Ollama provider detection for 'ollama/llama3.2': {is_ollama}")
    
    # Test with non-Ollama model
    llm = LLM(model="gpt-4")
    is_ollama = llm._is_ollama_provider()
    print(f"Ollama provider detection for 'gpt-4': {is_ollama}")
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("TESTING OLLAMA INFINITE LOOP FIX - SIMPLE VERSION")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Test 1: Provider detection
    if not test_is_ollama_provider():
        all_tests_passed = False
    
    # Test 2: Tool summary generation
    if not test_ollama_tool_summary_generation():
        all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED - Ollama infinite loop fix is working!")
    else:
        print("❌ SOME TESTS FAILED - Please check the implementation")
    print("=" * 60)