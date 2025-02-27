from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language

agent = Agent(
    instructions="You are a Wikipedia Agent", 
    tools=[wiki_search, wiki_summary, wiki_page, wiki_random, wiki_language],
    llm="openai/gpt-4o-mini",
    verbose=10
)
agent.start("history of AI")