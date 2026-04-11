from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Session Demo Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant.",
    ),
)

agent = Agent(name="session-demo", backend=managed)

# Run a task to create agent + session
agent.start("Say hello briefly")

# List sessions for this agent
sessions = managed.list_sessions()
print(f"Total sessions: {len(sessions)}")
for s in sessions[:5]:
    print(f"  ID: {s['id']}")
    print(f"  Status: {s['status']}")
    print(f"  Title: {s['title']}")
    print()
