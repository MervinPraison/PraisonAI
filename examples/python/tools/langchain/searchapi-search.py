from praisonaiagents import Agent, PraisonAIAgents
from langchain_community.utilities import SearchApiAPIWrapper

data_agent = Agent(instructions="I am looking for the top google searches of 2025", tools=[SearchApiAPIWrapper])
editor_agent = Agent(instructions="Analyze the data and derive insights")

agents = PraisonAIAgents(agents=[data_agent, editor_agent])
agents.start()