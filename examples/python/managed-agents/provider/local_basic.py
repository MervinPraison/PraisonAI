"""Local agent — basic local execution with gpt-4o-mini.

No external infrastructure needed. Runs the agent loop locally.
Uses the new canonical LocalAgent class for clarity.
"""
from praisonai import Agent
from praisonai.integrations import LocalAgent, LocalAgentConfig

# Create a local agent (runs locally, no managed runtime)
managed = LocalAgent(
    config=LocalAgentConfig(
        model="gpt-4o-mini",
        system="You are a helpful assistant. Be concise.",
        name="LocalAgent",
    ),
)

agent = Agent(name="local-basic", backend=managed)

# 1. Basic execution
print("[1] Basic execution...")
result = agent.start("What is the capital of France? One word.", stream=True)
print(f"    Result: {result}")

# 2. Agent metadata
print(f"\n[2] Agent ID: {managed.agent_id}")
print(f"    Version: {managed.agent_version}")
print(f"    Env ID:  {managed.environment_id}")
print(f"    Session: {managed.session_id}")

# 3. Multi-turn (same session keeps context)
print("\n[3] Multi-turn...")
result = agent.start("What country is that city in?", stream=True)
print(f"    Result: {result}")

# 4. Usage tracking
info = managed.retrieve_session()
print(f"\n[4] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# 5. List sessions
sessions = managed.list_sessions()
print(f"\n[5] Sessions: {len(sessions)}")
for s in sessions:
    print(f"    {s['id']} | {s['status']}")

print("\nDone!")
