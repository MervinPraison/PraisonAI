from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="My Agent v1",
        model="claude-haiku-4-5",
        system="You are a helpful assistant.",
    ),
)

agent = Agent(name="updatable", backend=managed)

# First call creates the agent
result = agent.start("Say hello briefly")
print(f"Created: {managed.agent_id}, version: {managed.agent_version}")

# Update the agent's system prompt (no need to recreate)
managed.update_agent(
    name="My Agent v2",
    system="You are a senior Python developer. Write production-quality code.",
)
print(f"Updated: {managed.agent_id}, version: {managed.agent_version}")
