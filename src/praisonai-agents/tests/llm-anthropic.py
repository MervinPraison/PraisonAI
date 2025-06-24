from praisonaiagents import Agent

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    llm="anthropic/claude-3-7-sonnet-20250219"
)
result = agent.start("Why Sky is Blue?")
print(result)

from praisonaiagents import Agent
from praisonaiagents.tools import internet_search

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[internet_search],
    llm="anthropic/claude-3-7-sonnet-20250219"
)
agent.start("What is Praison AI?")

from praisonaiagents import Agent, PraisonAIAgents
from praisonaiagents.tools import internet_search


research_agent = Agent(
    instructions="Search Information about Claude Sonnet 3.7", 
    tools=[internet_search],
    llm="anthropic/claude-3-7-sonnet-20250219"
)

editor_agent = Agent(
    instructions="Write a Blog Post with the provided information about Claude Sonnet 3.7", 
    llm="anthropic/claude-3-7-sonnet-20250219"
)

agents = PraisonAIAgents(agents=[research_agent, editor_agent])
result = agents.start()
print(result)