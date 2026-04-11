from praisonai import Agent, ManagedAgent, ManagedConfig

managed = ManagedAgent(
    config=ManagedConfig(
        name="Usage Tracker Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant.",
    ),
)

agent = Agent(name="tracker", backend=managed)
result = agent.start("Write a one-line Python script that prints the current date and run it")

print(result)
print("\nAgent finished.")

# Usage tracked automatically
print("\n--- Usage Report ---")
print(f"Input tokens:  {managed.total_input_tokens}")
print(f"Output tokens: {managed.total_output_tokens}")

# Or retrieve detailed session info from the API
info = managed.retrieve_session()
print(f"\nSession ID: {info.get('id')}")
print(f"Status: {info.get('status')}")
if "usage" in info:
    print(f"API Input tokens:  {info['usage']['input_tokens']}")
    print(f"API Output tokens: {info['usage']['output_tokens']}")
