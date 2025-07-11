from praisonaiagents import Agent

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

# Test the agent
agent = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="openai/gpt-4o-mini",
    tools=[get_stock_price, multiply],
    verbose=True  # Enable verbose to see what's happening
)

print("=== Testing Agent with Multiple Tools ===")
result = agent.start("multiply the Google stock price with 2")
print(f"\nFinal Result: {result}")
print(f"Result Type: {type(result)}")
print(f"Is None: {result is None}")
print(f"Is Empty String: {result == ''}")