from praisonai import Agent, ManagedAgent, ManagedConfig

# Agent, environment, and session are all created automatically on first use
managed = ManagedAgent(
    config=ManagedConfig(
        name="Coding Assistant",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant. Write clean, well-documented code.",
        session_title="Quickstart session",
    ),
)

agent = Agent(name="coder", backend=managed)
result = agent.start("Say hello")

print(f"Agent ID: {managed.agent_id}")
print(f"Environment ID: {managed.environment_id}")
print(f"Session ID: {managed.session_id}")
