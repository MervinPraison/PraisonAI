from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Session Demo",
        model="claude-haiku-4-5",
        system="You are a helpful assistant.",
    ),
)
agent = Agent(name="demo", backend=managed)

agent.start("Say hello and confirm you are ready.", stream=True)

print("\n--- IDs ---")
print(f"agent_id      : {managed.agent_id}")
print(f"environment_id: {managed.environment_id}")
print(f"session_id    : {managed.session_id}")
print(f"chat_history  : {len(agent.chat_history)} messages")

ids = managed.save_ids()
print(f"\nsave_ids(): {ids}")
