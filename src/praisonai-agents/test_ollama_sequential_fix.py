"""
Test script to reproduce and verify the fix for Ollama sequential tool calling issue.
The agent should:
1. Call get_stock_price to get Google's stock price (100)
2. Call multiply to multiply 100 by 2
3. Return the final result (200)

Issue: Ollama mixes arguments between tool calls, causing multiply to receive
{'a': 'get_stock_price', 'company_name': 'Google', 'b': '2'}
instead of {'a': 100, 'b': 2}

Fix: Added validation and filtering to remove invalid parameters from tool calls.
"""

import os
import logging
from praisonaiagents import Agent

# Enable debug logging to see the fix in action
logging.basicConfig(level=logging.DEBUG)

def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    print(f"[Tool Called] get_stock_price({company_name})")
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers
    
    Args:
        a (int): First number
        b (int): Second number
        
    Returns:
        int: Product of a and b
    """
    print(f"[Tool Called] multiply({a}, {b})")
    return a * b

# Test with working models first
print("=" * 60)
print("Testing with Gemini model (working baseline)")
print("=" * 60)

agent_gemini = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user. When asked to multiply a stock price, first get the stock price, then multiply it.",
    llm="gemini/gemini-2.5-pro",
    tools=[get_stock_price, multiply],
    verbose=True
)

try:
    result_gemini = agent_gemini.start("what is the stock price of Google? multiply the Google stock price with 2")
    print(f"\nFinal Result (Gemini): {result_gemini}")
except Exception as e:
    print(f"Gemini test failed: {e}")

# Test with Ollama (the failing case)
print("\n" + "=" * 60)
print("Testing with Ollama model (currently failing)")
print("=" * 60)

agent_ollama = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user. When asked to multiply a stock price, first get the stock price, then multiply it.",
    llm="ollama/llama3.2",
    tools=[get_stock_price, multiply],
    verbose=True
)

try:
    result_ollama = agent_ollama.start("what is the stock price of Google? multiply the Google stock price with 2")
    print(f"\nFinal Result (Ollama): {result_ollama}")
except Exception as e:
    print(f"Ollama test failed: {e}")
    import traceback
    traceback.print_exc()

# Verify results
print("\n" + "=" * 60)
print("Test Results Summary")
print("=" * 60)
print(f"Gemini result contains '200': {'200' in str(result_gemini) if 'result_gemini' in locals() else False}")
print(f"Ollama result contains '200': {'200' in str(result_ollama) if 'result_ollama' in locals() else False}")
print(f"Gemini returned empty: {'result_gemini' not in locals() or not result_gemini or result_gemini == ''}")
print(f"Ollama returned empty: {'result_ollama' not in locals() or not result_ollama or result_ollama == ''}")