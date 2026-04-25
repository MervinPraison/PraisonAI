"""Anthropic hosted runtime — entire agent runs on Anthropic's managed infrastructure.

Uses the new canonical HostedAgent class which clearly communicates that the entire
agent loop runs in Anthropic's cloud, not locally.
"""
from praisonai import Agent
from praisonai.integrations import HostedAgent, HostedAgentConfig

# Create a hosted agent running entirely on Anthropic's managed runtime
hosted = HostedAgent(
    provider="anthropic",
    config=HostedAgentConfig(
        model="claude-3-5-sonnet-latest",
        system="You are a helpful coding assistant. Be concise.",
        name="AnthropicHostedAgent",
        tools=[{"type": "agent_toolset_20260401"}],
    ),
)

agent = Agent(name="anthropic-hosted", backend=hosted)

# 1. Basic execution - runs entirely in Anthropic's cloud
print("[1] Hosted execution on Anthropic infrastructure...")
result = agent.start("What is the capital of France? One word.", stream=True)
print(f"    Result: {result}")

# 2. Agent metadata from Anthropic's API
print(f"\n[2] Agent ID: {hosted.agent_id}")
print(f"    Version: {hosted.agent_version}")
print(f"    Env ID:  {hosted.environment_id}")
print(f"    Session: {hosted.session_id}")

# 3. Multi-turn (same session keeps context in Anthropic's cloud)
print("\n[3] Multi-turn conversation...")
result = agent.start("What country is that city in?", stream=True)
print(f"    Result: {result}")

# 4. Usage tracking from Anthropic's usage API
info = hosted.retrieve_session()
print(f"\n[4] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# 5. List all sessions for this agent
sessions = hosted.list_sessions()
print(f"\n[5] Sessions: {len(sessions)}")
for s in sessions[:3]:  # Show first 3
    print(f"    {s['id']} | {s['status']}")

print("\nDone! Agent loop ran entirely on Anthropic's managed infrastructure.")