from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Research Agent",
        model="claude-haiku-4-5",
        system="You are a research assistant. Search the web for information.",
    ),
)

agent = Agent(name="researcher", backend=managed)
result = agent.start(
    "Search the web for the latest Python 3.13 features and summarize them in 3 bullet points"
)

print(result)
print("\nAgent finished.")
