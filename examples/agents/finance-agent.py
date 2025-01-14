from praisonaiagents import Agent, Tools
from praisonaiagents.tools import get_stock_price, get_stock_info, get_historical_data

agent = Agent(instructions="You are a Research Agent", tools=[get_stock_price, get_stock_info, get_historical_data])
agent.start("Understand current stock price and historical data of Apple and Google. Tell me if I can invest in them")