"""Simplest Planning Mode Example - Just enable planning=True"""

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agents
researcher = Agent(name="Researcher", role="Research Analyst")
writer = Agent(name="Writer", role="Content Writer")

# Create tasks
task1 = Task(description="Research the benefits of meditation", agent=researcher)
task2 = Task(description="Write a short article about meditation benefits", agent=writer)

# Run with planning enabled - that's it!
agents = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[task1, task2],
    planning=True,
    auto_approve_plan=True  # Auto-approve the generated plan
)

agents.start()
