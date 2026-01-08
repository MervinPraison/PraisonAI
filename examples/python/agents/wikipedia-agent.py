from praisonaiagents import Agent, Task, Agents
from praisonaiagents.tools import wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language],
    reflection=True,
    
    
)
agent.start(
    "What is the history of AI?"
    "First search the history of AI"
    "Read the page of the history of AI"
    "Get the summary of the page"
)