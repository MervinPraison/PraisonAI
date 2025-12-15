from praisonaiagents import Agent
from praisonaiagents.planning import PlanningAgent

def search_web(query: str) -> str:
    return f"Results for '{query}': LLMs, multimodal AI, autonomous agents"

researcher = Agent(name="Researcher", role="Research Analyst", llm="gpt-4o-mini")
writer = Agent(name="Writer", role="Content Writer", llm="gpt-4o-mini")

print("\n=== TEST 1: Basic Planning (NO tools) ===")
planner1 = PlanningAgent(llm="gpt-4o-mini")
plan1 = planner1.create_plan_sync(
    request="Write about AI trends 2025",
    agents=[researcher, writer]
)
print(f"Plan: {plan1.name}, Steps: {len(plan1.steps)}")

print("\n=== TEST 2: Planning WITH tools ===")
planner2 = PlanningAgent(llm="gpt-4o-mini", tools=[search_web])
plan2 = planner2.create_plan_sync(
    request="Write about AI trends 2025",
    agents=[researcher, writer]
)
print(f"Plan: {plan2.name}, Steps: {len(plan2.steps)}")

print("\n=== TEST 3: Planning WITH tools + reasoning ===")
planner3 = PlanningAgent(llm="gpt-4o-mini", tools=[search_web], reasoning=True)
plan3 = planner3.create_plan_sync(
    request="Write about AI trends 2025",
    agents=[researcher, writer]
)
print(f"Plan: {plan3.name}, Steps: {len(plan3.steps)}")

print("\n✅ Done!")
