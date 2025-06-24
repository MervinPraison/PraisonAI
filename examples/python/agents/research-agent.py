from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

agent = Agent(instructions="You are a Research Agent", tools=[duckduckgo])
agent.start("Research about AI 2024")