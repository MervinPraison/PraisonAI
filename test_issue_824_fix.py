#!/usr/bin/env python3
"""
Test for issue #824: Sequential Tool Calling Failure
This test verifies that the fix allows sequential tool calling for all tools,
not just the "sequentialthinking" tool.
"""

import os
import sys
from praisonaiagents import Agent

# Define test tools
def get_stock_price(company_name: str) -> str:
    """Get the stock price of a company"""
    print(f"🔧 Tool called: get_stock_price('{company_name}')")
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    print(f"🔧 Tool called: multiply({a}, {b})")
    return a * b

def test_sequential_tool_calling(llm_model=None, stream=True):
    """Test sequential tool calling with specified LLM model and stream setting"""
    print(f"\n{'='*60}")
    print(f"Testing Sequential Tool Calling")
    print(f"LLM: {llm_model or 'default'}")
    print(f"Stream: {stream}")
    print(f"{'='*60}")
    
    try:
        # Create agent with tools
        agent = Agent(
            instructions="You are a helpful assistant. Use the tools provided to help the user.",
            llm=llm_model,
            self_reflect=False,
            verbose=True,
            tools=[get_stock_price, multiply],
            stream=stream
        )
        
        # Test query that requires sequential tool calls
        query = "Get the stock price of Google and multiply it by 2"
        print(f"\n📝 Query: {query}")
        print("-" * 60)
        
        result = agent.chat(query, stream=stream)
        
        print("-" * 60)
        print(f"✅ Final Result: {result}")
        
        # Verify the result contains the expected calculation
        if "200" in str(result):
            print("✅ Test PASSED: Sequential tool calling worked correctly!")
            return True
        else:
            print("❌ Test FAILED: Expected result to contain '200' (100 * 2)")
            return False
            
    except Exception as e:
        print(f"❌ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run tests with different configurations"""
    print("🚀 Testing Sequential Tool Calling Fix for Issue #824")
    
    test_configs = [
        # Test with different streaming modes
        {"llm": None, "stream": False, "name": "Default LLM (non-streaming)"},
        {"llm": None, "stream": True, "name": "Default LLM (streaming)"},
    ]
    
    # Add Gemini test if API key is available
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        test_configs.extend([
            {"llm": "gemini/gemini-2.0-flash-exp", "stream": False, "name": "Gemini (non-streaming)"},
            {"llm": "gemini/gemini-2.0-flash-exp", "stream": True, "name": "Gemini (streaming)"},
        ])
    
    results = []
    for config in test_configs:
        print(f"\n\n{'#'*60}")
        print(f"# {config['name']}")
        print(f"{'#'*60}")
        
        passed = test_sequential_tool_calling(config["llm"], config["stream"])
        results.append((config["name"], passed))
    
    # Summary
    print(f"\n\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("✅ ALL TESTS PASSED!")
        print("Sequential tool calling is working correctly for all configurations.")
    else:
        print("❌ SOME TESTS FAILED!")
        print("Sequential tool calling needs further investigation.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())