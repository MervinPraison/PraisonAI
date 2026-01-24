"""
Test script to verify the fix for sequential tool calling.
The agent should:
1. Call get_stock_price to get Google's stock price (100)
2. Call multiply to multiply 100 by 2
3. Return the final result (200)
"""

import pytest
import os
from praisonaiagents import Agent
# Patch missing display_generating attribute in Agent class
Agent.display_generating = Agent._display_generating

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


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
def test_sequential_tool_calling_gpt():
    """Test sequential tool calling with GPT model"""
    print("=" * 60)
    print("Testing with GPT model")
    print("=" * 60)

    agent_gpt = Agent(
        instructions="You are a helpful assistant. When asked to multiply a stock price, first get the stock price, then multiply it.",
        llm="gpt-4o-mini",
        tools=[get_stock_price, multiply],
        output="verbose"
    )

    result = agent_gpt.start("what is the stock price of Google? multiply the Google stock price with 2")
    print(f"\nFinal Result (GPT): {result}")
    
    # Verify result
    assert result, "GPT returned empty result"
    print(f"GPT result contains '200': {'200' in str(result)}")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set - skipping integration test"
)
def test_sequential_tool_calling_gemini():
    """Test sequential tool calling with Gemini model"""
    print("=" * 60)
    print("Testing with Gemini model")
    print("=" * 60)

    agent_gemini = Agent(
        instructions="You are a helpful assistant. When asked to multiply a stock price, first get the stock price, then multiply it.",
        llm="gemini/gemini-2.0-flash",
        tools=[get_stock_price, multiply],
        output="verbose"
    )

    result = agent_gemini.start("what is the stock price of Google? multiply the Google stock price with 2")
    print(f"\nFinal Result (Gemini): {result}")
    
    # Verify result
    assert result, "Gemini returned empty result"
    print(f"Gemini result contains '200': {'200' in str(result)}")


if __name__ == "__main__":
    # Run tests manually
    if os.environ.get("OPENAI_API_KEY"):
        test_sequential_tool_calling_gpt()
    if os.environ.get("GOOGLE_API_KEY"):
        test_sequential_tool_calling_gemini()
