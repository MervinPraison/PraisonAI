from praisonaiagents import Agent

def search_web(query: str) -> str:
    return "AI trends: LLMs, multimodal AI, autonomous agents, edge AI"

print("=" * 60)
print("TEST 1: Planning ONLY (no tools, no reasoning)")
print("=" * 60)

agent1 = Agent(
    name="Assistant",
    llm="gpt-4o-mini",
    planning=True,
    verbose=False
)
result1 = agent1.start("Write 2 sentences about AI in healthcare")
print(f"\nResult: {result1[:200]}...")

print("\n" + "=" * 60)
print("TEST 2: Planning + Tools (no reasoning)")
print("=" * 60)

agent2 = Agent(
    name="Assistant",
    llm="gpt-4o-mini",
    planning=True,
    planning_tools=[search_web],
    verbose=False
)
result2 = agent2.start("Write 2 sentences about AI trends")
print(f"\nResult: {result2[:200]}...")

print("\n" + "=" * 60)
print("TEST 3: Planning + Tools + Reasoning")
print("=" * 60)

agent3 = Agent(
    name="Assistant",
    llm="gpt-4o-mini",
    planning=True,
    planning_tools=[search_web],
    planning_reasoning=True,
    verbose=False
)
result3 = agent3.start("Write 2 sentences about AI trends")
print(f"\nResult: {result3[:200]}...")

print("\n" + "=" * 60)
print("TEST 4: No Planning (direct execution)")
print("=" * 60)

agent4 = Agent(
    name="Assistant",
    llm="gpt-4o-mini",
    verbose=False
)
result4 = agent4.start("Write 2 sentences about AI trends")
print(f"\nResult: {result4[:200]}...")

print("\n" + "=" * 60)
print("COMPARISON COMPLETE")
print("=" * 60)
