"""Local agent loop with Gemini LLM — runs locally, not in a managed runtime.

Uses the new canonical LocalAgent class which clearly communicates that only the
agent loop runs locally. The LLM calls go to Google's Gemini API, but there's no managed runtime involved.
"""
from praisonai import Agent
from praisonai.integrations import LocalAgent, LocalAgentConfig

# Create a local agent using Gemini LLM
local = LocalAgent(
    config=LocalAgentConfig(
        model="gemini/gemini-2.0-flash",  # Use Gemini with litellm routing prefix
        system="You are a helpful coding assistant. Be concise.",
        name="LocalGeminiAgent",
        tools=["execute_command", "read_file", "write_file"],
    ),
)

agent = Agent(name="local-gemini", backend=local)

# 1. Basic execution - agent loop runs locally, LLM calls go to Gemini
print("[1] Local execution with Gemini LLM...")
result = agent.start("What is the capital of France? One word.", stream=True)
print(f"    Result: {result}")

# 2. Agent metadata (locally generated UUIDs)
print(f"\n[2] Agent ID: {local.agent_id}")
print(f"    Version: {local.agent_version}")
print(f"    Env ID:  {local.environment_id}")
print(f"    Session: {local.session_id}")

# 3. Multi-turn conversation (session state maintained locally)
print("\n[3] Multi-turn conversation...")
result = agent.start("What country is that city in?", stream=True)
print(f"    Result: {result}")

# 4. Usage tracking (accumulated locally)
info = local.retrieve_session()
print(f"\n[4] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# 5. Tool execution (runs in local subprocess)
print("\n[5] Tool execution example...")
result = agent.start("Create a file called hello_gemini.txt with 'Hello from Gemini agent!'", stream=True)
print(f"    Tool result: {result}")

print("\nDone! Agent loop ran locally with Gemini LLM calls.")