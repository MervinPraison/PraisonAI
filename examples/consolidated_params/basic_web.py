"""
Basic Web Search Example - Agent-Centric API

Demonstrates web search with consolidated params.
Presets: duckduckgo, tavily, google, bing, serper, search_only, fetch_only
"""

from praisonaiagents import Agent

# Basic: Enable web search with preset
agent = Agent(
    instructions="You are a research assistant with web access.",
    web="search_only",  # Compatible across models without web_fetch
)

if __name__ == "__main__":
    response = agent.start("What are the latest AI developments in 2024?")
    print(response)
