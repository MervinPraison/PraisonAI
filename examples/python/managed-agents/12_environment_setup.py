from praisonai import Agent, ManagedAgent, ManagedConfig

# Just add packages to the config — environment is created automatically
managed = ManagedAgent(
    config=ManagedConfig(
        name="Data Science Agent",
        model="claude-haiku-4-5",
        system="You are a data science assistant.",
        packages={"pip": ["pandas", "numpy"]},
    ),
)

agent = Agent(name="data-scientist", backend=managed)

print(f"Environment ID: {managed.environment_id}")

result = agent.start(
    "Create a Python script that generates random sales data with pandas and saves a summary to sales_summary.txt"
)

print(result)
print("\nAgent finished.")
