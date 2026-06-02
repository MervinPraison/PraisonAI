"""Anthropic managed runtime — full agent loop runs in Anthropic's cloud.

The ENTIRE loop (LLM calls, tool execution, memory, sessions) runs remotely
on Anthropic's managed infrastructure. This is the only provider today where
"the whole thing runs in that cloud".

Requires: ANTHROPIC_API_KEY environment variable set.
"""
import os

if not os.getenv("ANTHROPIC_API_KEY"):
    print("[skip] ANTHROPIC_API_KEY not set — set it to run this example.")
    raise SystemExit(0)

try:
    import anthropic  # noqa: F401  (required by AnthropicManagedAgent)
except ImportError:
    print("[skip] 'anthropic' SDK not installed — pip install 'anthropic>=0.94.0'")
    raise SystemExit(0) from None

try:
    from praisonai import Agent, ManagedAgent, ManagedConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None

managed = ManagedAgent(
    provider="anthropic",
    config=ManagedConfig(
        model="claude-3-5-sonnet-latest",
        system="You are a concise coding assistant. One-sentence answers.",
        name="AnthropicRuntimeAgent",
    ),
)
agent = Agent(name="anthropic-runtime", backend=managed)

# 1. Agent work entirely in the cloud
print("[1] Agent:", agent.start("Write a Python one-liner that sums 1..10. Just the code."))

# 2. Multi-turn reuses the same cloud session
print("[2] Agent:", agent.start("Now change it to factorial of 5."))

# 3. Cloud-side session metadata
info = managed.retrieve_session()
print(f"[3] session={managed.session_id}  status={info.get('status')}  "
      f"in={info.get('usage', {}).get('input_tokens', 0)}  "
      f"out={info.get('usage', {}).get('output_tokens', 0)}")
