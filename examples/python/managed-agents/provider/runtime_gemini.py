"""Gemini managed runtime — agent loop local, LLM calls go to Google's cloud.

``ManagedAgent(provider="gemini")`` wires a local managed loop to Gemini's
hosted models via litellm.

Requires: GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable set.
"""
import os

if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
    print("[skip] GEMINI_API_KEY / GOOGLE_API_KEY not set — set one to run this example.")
    raise SystemExit(0)

try:
    from praisonai import Agent, ManagedAgent, LocalManagedConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None

managed = ManagedAgent(
    provider="gemini",
    config=LocalManagedConfig(
        # Use explicit litellm prefix to guarantee routing to Google
        model="gemini/gemini-2.0-flash-exp",
        system="You are a concise assistant. One-sentence answers.",
        name="GeminiRuntimeAgent",
    ),
)
agent = Agent(name="gemini-runtime", backend=managed)

# 1. Agent work (LLM call goes to Google cloud)
print("[1] Agent:", agent.start("What does REST stand for? One sentence."))

# 2. Multi-turn reuses the session
print("[2] Agent:", agent.start("How is it different from GraphQL?"))

info = managed.retrieve_session()
print(f"[3] session={managed.session_id}  "
      f"in={info.get('usage', {}).get('input_tokens', 0)}  "
      f"out={info.get('usage', {}).get('output_tokens', 0)}")
