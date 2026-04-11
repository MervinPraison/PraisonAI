from praisonai import Agent, ManagedAgent, ManagedConfig

# Select specific tools: only bash, read, write — everything else disabled
managed = ManagedAgent(
    config=ManagedConfig(
        name="Bash Only Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant that can only use bash commands.",
        tools=[
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [
                    {"name": "bash", "enabled": True},
                    {"name": "read", "enabled": True},
                    {"name": "write", "enabled": True},
                ],
            },
        ],
    ),
)

agent = Agent(name="bash-agent", backend=managed)
result = agent.start("List the current directory contents and show system info using uname -a")

print(result)
print("\nAgent finished.")
