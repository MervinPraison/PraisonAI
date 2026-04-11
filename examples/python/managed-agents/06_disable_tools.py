from praisonai import Agent, ManagedAgent, ManagedConfig

# Disable specific tools: web access disabled, everything else stays on
managed = ManagedAgent(
    config=ManagedConfig(
        name="No Web Agent",
        model="claude-haiku-4-5",
        system="You are a coding assistant. You cannot access the web.",
        tools=[
            {
                "type": "agent_toolset_20260401",
                "configs": [
                    {"name": "web_fetch", "enabled": False},
                    {"name": "web_search", "enabled": False},
                ],
            },
        ],
    ),
)

agent = Agent(name="no-web-agent", backend=managed)
result = agent.start("Write a hello world Python script and run it")

print(result)
print("\nAgent finished.")
