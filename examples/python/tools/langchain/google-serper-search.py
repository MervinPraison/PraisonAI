from praisonaiagents import Agent, PraisonAIAgents
from langchain_community.utilities import GoogleSerperAPIWrapper
import os
from dotenv import load_dotenv

load_dotenv()

os.environ['SERPER_API_KEY'] = os.getenv('SERPER_API_KEY')

search = GoogleSerperAPIWrapper()

data_agent = Agent(instructions="Suggest me top 5 most visited websites for Dosa Recipe", tools=[search])
editor_agent = Agent(instructions="List out the websites with their url and a short description")
agents = PraisonAIAgents(agents=[data_agent, editor_agent])
agents.start()