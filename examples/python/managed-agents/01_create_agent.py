from praisonai import Agent, ManagedAgent

# Zero config — defaults: name="Agent", model="claude-haiku-4-5"
managed = ManagedAgent()
agent = Agent(name="coder", backend=managed)
result = agent.start("Say hello")

print(f"Agent ID: {managed.agent_id}")
print(f"Version: {managed.agent_version}")
