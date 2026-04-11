from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Coding Assistant",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant. Write clean, well-documented code.",
    ),
)

agent = Agent(name="coder", backend=managed)

result = agent.start(
    "Create a Python script that generates the first 20 Fibonacci numbers and saves them to fibonacci.txt",
    stream=True,
)

print("\nAgent finished.")
