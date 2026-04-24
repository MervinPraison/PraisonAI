"""OpenAI managed runtime — agent loop local, LLM calls go to OpenAI cloud.

``ManagedAgent(provider="openai")`` wires a local managed loop to OpenAI's
hosted models. The LLM reasoning (the heavy-lifting) runs in OpenAI's cloud;
the agent orchestration (tool routing, session state) runs in this process.

Requires: OPENAI_API_KEY environment variable set.
"""
import os

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set — set it to run this example.")
    raise SystemExit(0)

try:
    from praisonai import Agent, ManagedAgent, LocalManagedConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None

managed = ManagedAgent(
    provider="openai",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a concise assistant. One-sentence answers.",
        name="OpenAIRuntimeAgent",
    ),
)
agent = Agent(name="openai-runtime", backend=managed)

# 1. Agent work (LLM call goes to OpenAI cloud)
print("[1] Agent:", agent.start("What is the time complexity of binary search? One sentence."))

# 2. Multi-turn reuses the session
print("[2] Agent:", agent.start("And for a linear scan?"))

# 3. Local session metadata (cloud usage accumulated)
info = managed.retrieve_session()
print(f"[3] session={managed.session_id}  "
      f"in={info.get('usage', {}).get('input_tokens', 0)}  "
      f"out={info.get('usage', {}).get('output_tokens', 0)}")
