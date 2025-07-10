from praisonaiagents import AutoAgents
from praisonaiagents.tools import duckduckgo

# Create AutoAgents instance
agents = AutoAgents(
    instructions="Search for information about AI Agents",
    tools=[duckduckgo],
    process="sequential",
    verbose=True,
    max_agents=3  # Maximum number of agents to create
)

# Start the agents
result = agents.start()
print(result)

##or

from praisonaiagents import AutoAgents
from praisonaiagents.tools import (
    evaluate, solve_equation, convert_units,
    calculate_statistics, calculate_financial
)


def get_stock_price(company_name: str) -> str:
    """
    Get the stock price of a company
    
    Args:
        company_name (str): The name of the company
        
    Returns:
        str: The stock price of the company
    """

    if company_name.lower() == "apple" or company_name.lower() == "aapl":
        return f"The stock price of {company_name} is 100"
    elif company_name.lower() == "google" or company_name.lower() == "googl":
        return f"The stock price of {company_name} is 200"
    else:
        return f"The stock price of {company_name} is 50"

# Create AutoAgents instance  
agents = AutoAgents(
    instructions="Get the stock price of google and compare it to the stock price of apple",
    tools=[evaluate, get_stock_price],
    process="sequential",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    self_reflect=False,
    verbose=False,
    max_agents=3  # Maximum number of agents to create
)

# Start the agents
result = agents.start()
print(result)