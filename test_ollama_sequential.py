"""
Test script for Ollama sequential tool calling fix
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

# Test with Ollama model
print("Testing Ollama sequential tool calling...")
print("=" * 50)

agent = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="ollama/qwen3",
    tools=[get_stock_price, multiply],
    verbose=True
)

result = agent.start("what is the stock price of Google? multiply the Google stock price with 2")
print(f"\nFinal Result: {result}")

# Verify the result
if result:
    result_lower = str(result).lower()
    if "200" in result_lower or "two hundred" in result_lower:
        print("\n✅ SUCCESS: Sequential tool calling worked correctly!")
        print("The agent successfully:")
        print("1. Called get_stock_price('Google') → returned '100'")
        print("2. Called multiply(100, 2) → returned '200'")
        print("3. Provided the final answer containing '200'")
    else:
        print("\n⚠️  WARNING: Result doesn't contain expected value '200'")
        print(f"Got: {result}")
else:
    print("\n❌ FAILED: Result is None or empty")
    print("The agent should have returned a response with the calculated value")