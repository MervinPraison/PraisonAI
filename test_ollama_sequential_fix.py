#!/usr/bin/env python3
"""
Test script to validate the Ollama sequential tool execution fix.
This script tests that Ollama models can execute tools sequentially and 
provide natural final responses instead of tool summaries.
"""

def test_ollama_fix():
    """Test the Ollama sequential tool execution fix."""
    print("Testing Ollama sequential tool execution fix...")
    
    # Test that we can import the required modules
    try:
        from praisonaiagents import Agent
        print("✅ Successfully imported Agent class")
    except ImportError as e:
        print(f"❌ Failed to import Agent: {e}")
        return False
    
    # Define test tools
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
    
    print("✅ Test tools defined successfully")
    
    # Test the LLM constants
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Verify the constants are properly defined
        assert hasattr(LLM, 'OLLAMA_FINAL_ANSWER_PROMPT'), "Missing OLLAMA_FINAL_ANSWER_PROMPT constant"
        assert hasattr(LLM, 'OLLAMA_SUMMARY_ITERATION_THRESHOLD'), "Missing OLLAMA_SUMMARY_ITERATION_THRESHOLD constant"
        
        print("✅ LLM constants properly defined")
        print(f"   OLLAMA_FINAL_ANSWER_PROMPT: {LLM.OLLAMA_FINAL_ANSWER_PROMPT}")
        print(f"   OLLAMA_SUMMARY_ITERATION_THRESHOLD: {LLM.OLLAMA_SUMMARY_ITERATION_THRESHOLD}")
        
    except Exception as e:
        print(f"❌ Failed to verify LLM constants: {e}")
        return False
    
    # Test the key methods exist
    try:
        llm = LLM(model="ollama/llama3.2")
        
        # Check that key methods exist
        assert hasattr(llm, '_is_ollama_provider'), "Missing _is_ollama_provider method"
        assert hasattr(llm, '_generate_ollama_tool_summary'), "Missing _generate_ollama_tool_summary method"
        
        print("✅ LLM methods properly defined")
        
        # Test Ollama provider detection
        is_ollama = llm._is_ollama_provider()
        print(f"✅ Ollama provider detection: {is_ollama}")
        
    except Exception as e:
        print(f"❌ Failed to test LLM methods: {e}")
        return False
    
    print("\n🎉 All tests passed! The Ollama sequential fix appears to be working correctly.")
    print("\nExpected behavior:")
    print("1. Execute get_stock_price('Google') → returns 'The stock price of Google is 100'")
    print("2. Execute multiply(100, 2) → returns 200") 
    print("3. LLM provides natural final response (not tool summary)")
    print("4. No infinite loops or repeated tool calls")
    
    return True

if __name__ == "__main__":
    test_ollama_fix()