"""
Basic Knowledge (RAG) Example - Agent-Centric API

Demonstrates knowledge with consolidated params.
Supports: bool, list of sources, dict config, KnowledgeConfig
"""

from praisonaiagents import Agent

# Basic: Enable knowledge with list of sources
agent = Agent(
    instructions="You are a helpful assistant with document knowledge.",
    knowledge=["docs/"],  # List of file/folder paths
)

if __name__ == "__main__":
    response = agent.start("What does the documentation say about installation?")
    print(response)
