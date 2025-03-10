# pip install langchain-community google-search-results
# export SERPAPI_API_KEY=your_api_key_here
# export OPENAI_API_KEY=your_api_key_here

from langchain_community.utilities.google_trends import GoogleTrendsAPIWrapper
from praisonaiagents import Agent, PraisonAIAgents

research_agent = Agent(
    instructions="Research trending topics related to AI",
    tools=[GoogleTrendsAPIWrapper]
)

summarise_agent = Agent(
    instructions="Summarise findings from the research agent",
)

agents = PraisonAIAgents(agents=[research_agent, summarise_agent])
agents.start()