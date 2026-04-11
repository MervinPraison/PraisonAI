from praisonai import Agent, ManagedAgent, ManagedConfig

# Environment is created automatically — just specify packages/networking in config
managed = ManagedAgent(
    config=ManagedConfig(
        name="Coding Assistant",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant. Write clean, well-documented code.",
        networking={"type": "unrestricted"},
    ),
)

agent = Agent(name="coder", backend=managed)
result = agent.start("Say hello")

print(f"Agent ID: {managed.agent_id}")
print(f"Environment ID: {managed.environment_id}")
