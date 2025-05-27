from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language],
    self_reflect=True,
    min_reflect=3,
    max_reflect=5,
)
agent.start(
    "What is the history of AI?"
    "First search the history of AI"
    "Read the page of the history of AI"
    "Get the summary of the page"
)