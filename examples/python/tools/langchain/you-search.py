from praisonaiagents import Agent, Agents
from langchain_community.utilities.you import YouSearchAPIWrapper

data_agent = Agent(instructions="Gather the weather data for Barcelona", tools=[YouSearchAPIWrapper])
editor_agent = Agent(instructions="Breifly describe the weather in Barcelona")

agents = AgentManager(agents=[data_agent, editor_agent])
agents.start()