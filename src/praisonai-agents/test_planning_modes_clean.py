from praisonaiagents import Agent, Task, PraisonAIAgents

def search_web(query: str) -> str:
    return f"Results: AI trends include LLMs, multimodal AI, autonomous agents"

researcher = Agent(name="Researcher", role="Research Analyst", llm="gpt-4o-mini")
writer = Agent(name="Writer", role="Content Writer", llm="gpt-4o-mini")

task1 = Task(description="Research AI trends in 2025", agent=researcher)
task2 = Task(description="Write a 2 sentence summary", agent=writer)

agents = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[task1, task2],
    planning=True,
    planning_tools=[search_web],
    planning_reasoning=True,
    auto_approve_plan=True
)

result = agents.start()
print(result)
