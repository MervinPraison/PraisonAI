from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Multi Turn Agent",
        model="claude-haiku-4-5",
        system="You are a helpful coding assistant.",
    ),
)

agent = Agent(name="multi-turn", backend=managed)
print(f"Session ID: {managed.session_id}")

# Multi-turn: each call reuses the same session — agent remembers context
messages = [
    "Create a file called greeting.py that prints 'Hello World'",
    "Now modify greeting.py to accept a name as a command line argument",
    "Run greeting.py with the argument 'Claude'",
]

for i, message in enumerate(messages):
    print(f"\n--- Turn {i + 1}: {message} ---\n")
    result = agent.start(message)
    print(result)
    print("\nAgent finished turn.")
