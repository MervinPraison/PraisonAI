"""Simplest Planning Mode Example - Just enable planning=True"""

from praisonaiagents import Agent, Task, AgentTeam

# Create agents
researcher = Agent(name="Researcher", role="Research Analyst")
writer = Agent(name="Writer", role="Content Writer")

# Create tasks
task1 = Task(description="Research the benefits of meditation", agent=researcher)
task2 = Task(description="Write a short article about meditation benefits", agent=writer)

# Run with planning enabled - that's it!
agents = AgentTeam(
    agents=[researcher, writer],
    tasks=[task1, task2],
    planning=True
)

agents.start()
