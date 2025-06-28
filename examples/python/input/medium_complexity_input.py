"""
Medium Complexity Input Example for PraisonAI

This example shows how to use multiple user inputs to create a more sophisticated
agent system with tools, multiple agents, and context passing between tasks.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

# Get multiple inputs
topic = input("Enter search topic: ")
num_results = input("How many results? (default: 5): ") or "5"

# Create search agent with tools
search_agent = Agent(
    name="WebSearcher",
    role="Search Specialist",
    goal=f"Find {num_results} relevant results about {topic}",
    backstory="Expert in internet research and data collection",
    tools=[duckduckgo],
    self_reflect=False
)

# Create analysis agent
analysis_agent = Agent(
    name="Analyzer",
    role="Data Analyst",
    goal="Analyze and summarize search results",
    backstory="Expert in data synthesis and reporting"
)

# Create tasks with context passing
search_task = Task(
    description=f"Search for '{topic}' and find top {num_results} results",
    expected_output=f"List of {num_results} relevant results with sources",
    agent=search_agent,
    name="search_task"
)

analyze_task = Task(
    description="Analyze the search results and create a summary report",
    expected_output="Comprehensive summary with key insights",
    agent=analysis_agent,
    context=[search_task],  # Receives results from search_task
    name="analysis_task"
)

# Run sequential process
agents = PraisonAIAgents(
    agents=[search_agent, analysis_agent],
    tasks=[search_task, analyze_task],
    process="sequential"
)
agents.start()