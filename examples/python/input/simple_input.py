"""
Simple Input Example for PraisonAI

This example demonstrates how to use basic user input to create dynamic agents and tasks.
The user is prompted for a search query, and the agent searches for information about it.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents

# Get user input
user_query = input("What would you like to search for? ")

# Create agent
agent = Agent(
    name="SearchAgent",
    role="Information Finder",
    goal="Find information about user's query",
    backstory="Expert researcher with web access"
)

# Create task with dynamic input
task = Task(
    description=f"Search for information about: {user_query}",
    expected_output=f"Summary of findings about {user_query}",
    agent=agent
)

# Run
agents = PraisonAIAgents(agents=[agent], tasks=[task])
agents.start()