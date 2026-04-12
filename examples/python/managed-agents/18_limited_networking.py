from praisonai import Agent, ManagedAgent, ManagedConfig

# Limited networking: restrict container to specific hosts only
managed = ManagedAgent(
    config=ManagedConfig(
        name="Restricted Network Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant with restricted network access.",
        networking={
            "type": "limited",
            "allowed_hosts": ["api.github.com"],
            "allow_mcp_servers": False,
            "allow_package_managers": True,
        },
    ),
)

agent = Agent(name="restricted", backend=managed)
result = agent.start(
    "Try to fetch https://api.github.com and report what you get. Then try https://example.com — it should fail.",
    stream=True,
)

print("\nAgent finished.")
