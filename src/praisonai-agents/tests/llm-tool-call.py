from praisonaiagents import Agent
from praisonaiagents.tools import wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language

agent1 = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language],
    llm="openai/gpt-4o-mini",
    verbose=10
)
agent1.start("history of AI in 1 line")

agent2 = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language],
    llm="gpt-4o-mini",
    verbose=10
)
agent2.start("history of AI in 1 line")