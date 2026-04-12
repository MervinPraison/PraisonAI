from praisonai import Agent, ManagedAgent, ManagedConfig

# Environment management: list, retrieve, archive, delete

managed = ManagedAgent(
    config=ManagedConfig(
        name="Env Management Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant.",
    ),
)
agent = Agent(name="env-mgmt", backend=managed)

# First call creates agent + environment + session
agent.start("Say hello briefly")

# Access the underlying Anthropic client for environment management
client = managed._get_client()
env_id = managed.environment_id
print(f"Environment ID: {env_id}")

# List all environments
environments = client.beta.environments.list()
print(f"\nTotal environments: {len(environments.data)}")
for env in environments.data[:5]:
    print(f"  {env.id} | {env.name} | {getattr(env, 'status', 'active')}")

# Retrieve a specific environment
env = client.beta.environments.retrieve(env_id)
print(f"\nRetrieved: {env.id} | {env.name}")

# Archive (read-only, existing sessions continue)
archived = client.beta.environments.archive(env_id)
print(f"Archived: {archived.id} | status: {getattr(archived, 'status', 'archived')}")

# Delete (only if no sessions reference it — may fail if sessions exist)
try:
    client.beta.environments.delete(env_id)
    print(f"Deleted: {env_id}")
except Exception as e:
    print(f"Delete skipped (expected if sessions exist): {e}")

print("\nEnvironment management complete.")
