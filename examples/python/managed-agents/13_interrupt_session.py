from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Interruptable Agent",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant.",
    ),
)

agent = Agent(name="interruptable", backend=managed)

# Start a task
result = agent.start("Write a Python script that prints numbers 1 to 5")
print(result)

# Interrupt the agent mid-work
print("\n[Sending interrupt...]")
managed.interrupt()
print("Agent stopped.")
