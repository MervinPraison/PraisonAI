from praisonaiagents import Agent, Task, PraisonAIAgents

def search_web(query: str) -> str:
    return "AI trends: LLMs, multimodal AI, autonomous agents"

agent = Agent(
    name="AI Assistant",
    role="Research and Writing Specialist",
    llm="gpt-4o-mini",
    instructions="Research AI trends in 2025 and write a 2 sentence summary"
)

task = Task(
    description="Research AI trends in 2025 and write a 2 sentence summary",
    agent=agent
)

agents = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    planning=True,
    planning_tools=[search_web],
    planning_reasoning=True,
    auto_approve_plan=True
)

result = agents.start()
print(result)
