"""Test sequential tool calling fix"""
from praisonaiagents import Agent

def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """
    print(f"Tool called: get_stock_price({company_name})")
    return f"The stock price of {company_name} is 100"

def multiply(a: int, b: int) -> int:
    """
    Multiply two numbers
    """
    print(f"Tool called: multiply({a}, {b})")
    return a * b

# Test with streaming disabled to verify the fix
print("Testing sequential tool calling with stream=False...")
agent = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    self_reflect=False,
    verbose=True,
    tools=[get_stock_price, multiply],
    stream=False  # Force non-streaming mode - use stream parameter directly
)

result = agent.chat("Get the stock price of Google and multiply it by 2")
print(f"\nFinal result: {result}")

# Test with default streaming mode
print("\n\nTesting sequential tool calling with default streaming...")
agent2 = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    self_reflect=False,
    verbose=True,
    tools=[get_stock_price, multiply]
)

result2 = agent2.chat("Get the stock price of Google and multiply it by 2")
print(f"\nFinal result: {result2}")
