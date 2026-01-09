"""Advanced memory example - with config and overrides."""
from praisonaiagents import Agent, MemoryConfig

# With full config
agent = Agent(
    instructions="You are a helpful assistant with memory.",
    memory=MemoryConfig(
        backend="redis",
        user_id="user123",
        session_id="session456",
        auto_memory=True,
    ),
)

# With array [preset, overrides]
agent_override = Agent(
    instructions="You are a helpful assistant.",
    memory=["redis", {"user_id": "custom_user"}],
)

if __name__ == "__main__":
    response = agent.chat("Remember that my favorite color is blue.")
    print(response)
