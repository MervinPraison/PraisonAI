from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

agent = Agent(instructions="You are a Planning Agent", tools=[duckduckgo])
agent.start("I want to go London next week, find me a good hotel and flight")