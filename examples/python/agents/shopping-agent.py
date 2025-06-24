from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

agent = Agent(instructions="You are a Shopping Agent", tools=[duckduckgo])
agent.start("I want to buy iPhone 16 Pro Max, check 5 stores and give me price in table")