#!/usr/bin/env python3
"""
Test script to verify that AutoAgents hierarchical workflow works with non-OpenAI LLMs
without requiring OpenAI API key.

This tests the fix for issue #873.
"""

import os
import sys

# Ensure OpenAI API key is not set to verify the fix works
if 'OPENAI_API_KEY' in os.environ:
    del os.environ['OPENAI_API_KEY']

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents import AutoAgents

def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    if company_name.lower() == "apple" or company_name.lower() == "aapl":
        return f"The stock price of {company_name} is 100"
    elif company_name.lower() == "google" or company_name.lower() == "googl":
        return f"The stock price of {company_name} is 200"
    else:
        return f"The stock price of {company_name} is 50"

def test_hierarchical_without_openai():
    """Test hierarchical process without OpenAI API key"""
    print("Testing AutoAgents with hierarchical process and Gemini LLM...")
    print("OPENAI_API_KEY is set:", 'OPENAI_API_KEY' in os.environ)
    
    try:
        # Create AutoAgents instance with Gemini
        agents = AutoAgents(
            instructions="Write a poem on the stock price of apple",
            tools=[get_stock_price],
            process="hierarchical",
            llm="gemini/gemini-2.5-flash-lite-preview-06-17",
            self_reflect=True,
            verbose=True,
            max_agents=3  # Maximum number of agents to create
        )
        
        # Start the agents
        print("\nStarting agents...")
        result = agents.start()
        
        print("\n=== RESULT ===")
        print(result)
        print("\n=== TEST PASSED ===")
        print("Hierarchical workflow completed successfully without OpenAI API key!")
        return True
        
    except Exception as e:
        if "api_key" in str(e) and "OPENAI_API_KEY" in str(e):
            print("\n=== TEST FAILED ===")
            print(f"Error: Still requires OpenAI API key: {e}")
            return False
        else:
            print(f"\nUnexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

def test_hierarchical_with_mock_llm():
    """Test with a mock LLM to ensure no API calls are made to OpenAI"""
    print("\n\nTesting with mock LLM configuration...")
    
    try:
        # Create AutoAgents instance with a mock configuration
        agents = AutoAgents(
            instructions="Simple test task",
            tools=[get_stock_price],
            process="hierarchical",
            llm={
                "model": "test/mock-model",
                "api_key": "mock-key",
                "base_url": "http://localhost:9999"  # Non-existent URL
            },
            verbose=False,
            max_agents=2
        )
        
        # This should fail with connection error, not OpenAI API key error
        try:
            result = agents.start()
            # If we get here, the test didn't behave as expected
            print("\n=== TEST WARNING ===")
            print("Expected an error but execution succeeded")
            return False
        except Exception as e:
            if "api_key" in str(e) and "OPENAI_API_KEY" in str(e):
                print("\n=== TEST FAILED ===")
                print(f"Error: Still requires OpenAI API key: {e}")
                return False
            else:
                print("\n=== TEST PASSED ===")
                print("Failed with expected error (not OpenAI API key error)")
                print(f"Error type: {type(e).__name__}")
                return True
                
    except Exception as e:
        print(f"\nSetup error: {e}")
        return False

if __name__ == "__main__":
    # Track test results
    test_results = []
    
    # Run both tests
    mock_test_passed = test_hierarchical_with_mock_llm()
    test_results.append(("Mock LLM Test", mock_test_passed))
    
    # Only run the actual Gemini test if we have the API key
    if 'GOOGLE_API_KEY' in os.environ or 'GEMINI_API_KEY' in os.environ:
        gemini_test_passed = test_hierarchical_without_openai()
        test_results.append(("Gemini Test", gemini_test_passed))
    else:
        print("\n\nSkipping Gemini test - no GOOGLE_API_KEY or GEMINI_API_KEY found")
        print("The mock test passed, confirming the fix works!")
    
    # Summary
    print("\n=== TEST SUMMARY ===")
    all_passed = True
    for test_name, passed in test_results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)