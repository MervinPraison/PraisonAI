from praisonaiagents import Agent, PraisonAIAgents
from langchain_community.tools import BraveSearch
import os

def search_brave(query: str):
    """Searches using BraveSearch and returns results."""
    api_key = os.environ['BRAVE_SEARCH_API']
    tool = BraveSearch.from_api_key(api_key=api_key, search_kwargs={"count": 3})
    return tool.run(query)

data_agent = Agent(instructions="Search on ways to boost lead generation through Linkedin", tools=[search_brave])
editor_agent = Agent(instructions="Layout a plan to use Linkedin as a Lead Generator tool")
agents = PraisonAIAgents(agents=[data_agent, editor_agent])
agents.start()
