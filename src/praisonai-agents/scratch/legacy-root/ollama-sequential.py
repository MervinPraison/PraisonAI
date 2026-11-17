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



agent = Agent(
    instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
    llm="ollama/llama3.2",
    tools=[get_stock_price, multiply]
)

result = agent.start("what is the stock price of Google? multiply the Google stock price with 2")
print(result)