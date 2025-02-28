from praisonaiagents import Agent
from praisonaiagents.tools import internet_search

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[internet_search],
    llm="anthropic/claude-3-7-sonnet-20250219",
    verbose=10
)
agent.start("history of AI in 1 line")
