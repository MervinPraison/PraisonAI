from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

agent = Agent(instructions="You are a Web Search Agent", tools=[duckduckgo])
agent.start("Search about AI 2024")