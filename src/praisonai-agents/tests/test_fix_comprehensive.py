"""
Test script to verify the fix for sequential tool calling.
The agent should:
1. Call get_stock_price to get Google's stock price (100)
2. Call multiply to multiply 100 by 2
3. Return the final result (200)
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

# Test with Gemini
print("=" * 60)
print("Testing with Gemini model")
print("=" * 60)

agent_gemini = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user. When asked to multiply a stock price, first get the stock price, then multiply it.",
    llm="gemini/gemini-2.5-pro",
    tools=[get_stock_price, multiply],
    verbose=True
)

result_gemini = agent_gemini.start("what is the stock price of Google? multiply the Google stock price with 2")
print(f"\nFinal Result (Gemini): {result_gemini}")

# Test with GPT-4
print("\n" + "=" * 60)
print("Testing with GPT-4 model")
print("=" * 60)

agent_gpt4 = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user. When asked to multiply a stock price, first get the stock price, then multiply it.",
    llm="gpt-4o",
    tools=[get_stock_price, multiply],
    verbose=True
)

result_gpt4 = agent_gpt4.start("what is the stock price of Google? multiply the Google stock price with 2")
print(f"\nFinal Result (GPT-4): {result_gpt4}")

# Verify results
print("\n" + "=" * 60)
print("Test Results Summary")
print("=" * 60)
print(f"Gemini result contains '200': {'200' in str(result_gemini) if result_gemini else False}")
print(f"GPT-4 result contains '200': {'200' in str(result_gpt4) if result_gpt4 else False}")
print(f"Gemini returned empty: {not result_gemini or result_gemini == ''}")
print(f"GPT-4 returned empty: {not result_gpt4 or result_gpt4 == ''}")
