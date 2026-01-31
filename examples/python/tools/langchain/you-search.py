from praisonaiagents import Agent, AgentTeam
from langchain_community.utilities.you import YouSearchAPIWrapper

data_agent = Agent(instructions="Gather the weather data for Barcelona", tools=[YouSearchAPIWrapper])
editor_agent = Agent(instructions="Breifly describe the weather in Barcelona")

agents = AgentTeam(agents=[data_agent, editor_agent])
agents.start()