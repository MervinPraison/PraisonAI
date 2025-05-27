from praisonaiagents import Agent, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

data_agent = Agent(instructions="Search and Read Research Papers on DNA Mutation", tools=[duckduckgo])
editor_agent = Agent(instructions="Write a scientifically researched outcome and findings about DNA Mutation")
agents = PraisonAIAgents(agents=[data_agent, editor_agent])
agents.start()