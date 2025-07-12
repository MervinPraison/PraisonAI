#!/usr/bin/env python3
"""
Test script to verify sequential tool execution works correctly with OpenAI client.
This demonstrates the fix for issue #845.
"""

from praisonaiagents import Agent

def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company

    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    print(f"[Tool Called] get_stock_price with company_name='{company_name}'")
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers
    """
    print(f"[Tool Called] multiply with a={a}, b={b}")
    return a * b

# Test with OpenAI client
print("Testing sequential tool execution with OpenAI client...")
print("-" * 60)

agent = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="gpt-4o",
    tools=[get_stock_price, multiply]
)

result = agent.start("what is the stock price of Google? multiply the Google stock price with 2")
print("\n" + "=" * 60)
print("FINAL RESULT:")
print(result)
print("=" * 60)

# Expected behavior:
# 1. The agent should call get_stock_price("Google") and get "100"
# 2. The agent should then call multiply(100, 2) and get "200"
# 3. The final response should mention both the stock price and the result of multiplication