from praisonaiagents import Agent

def search_web(query: str) -> str:
    return "AI trends: LLMs, multimodal AI, autonomous agents"

agent = Agent(
    name="AI Assistant",
    role="Research and Writing Specialist",
    llm="gpt-4o-mini",
    planning=True,
    planning_tools=[search_web],
    planning_reasoning=True,
    verbose=False  # Quiet mode
)

result = agent.start("Research AI trends in 2025 and write a 2 sentence summary")
print("\n=== FINAL RESULT ===")
print(result)
