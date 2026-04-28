"""Ollama managed runtime — agent runs against a local/self-hosted LLM.

``ManagedAgent(provider="ollama")`` wires the managed loop to an Ollama
server. Model runs locally (or on a self-hosted box) instead of in a public
cloud — useful when you want the "managed agent" developer experience with
no external API dependency.

Requires: An Ollama server reachable (default ``http://localhost:11434``)
with at least one model pulled (e.g., ``ollama pull llama3.2``).
"""
import os
import urllib.error
import urllib.request

base = os.getenv("OLLAMA_HOST", "http://localhost:11434")
try:
    urllib.request.urlopen(f"{base}/api/tags", timeout=2).read()
except (urllib.error.URLError, OSError) as e:
    print(f"[skip] Ollama not reachable at {base} ({e}). Start it with `ollama serve`.")
    raise SystemExit(0)

try:
    from praisonai import Agent, ManagedAgent, LocalManagedConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None

managed = ManagedAgent(
    provider="ollama",
    config=LocalManagedConfig(
        model="llama3.2",
        system="You are a concise assistant. One-sentence answers.",
        name="OllamaRuntimeAgent",
    ),
)
agent = Agent(name="ollama-runtime", backend=managed)

# 1. Agent work (LLM call goes to your Ollama server)
print("[1] Agent:", agent.start("What is the capital of Japan? One word."))

# 2. Multi-turn reuses the session
print("[2] Agent:", agent.start("Name its most famous mountain."))

info = managed.retrieve_session()
print(f"[3] session={managed.session_id}")
