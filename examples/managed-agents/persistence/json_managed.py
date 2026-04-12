#!/usr/bin/env python3
"""
ManagedAgent + JSON File Persistence — Real conversation with session resume.

Uses DefaultSessionStore (JSON files on disk). No external database required.

Prerequisites:
    pip install praisonai praisonaiagents
    export OPENAI_API_KEY="sk-..."
"""

import json
import os
import shutil
import sys
import tempfile

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig
from praisonaiagents import Agent
from praisonaiagents.session.store import DefaultSessionStore

SESSION_DIR = os.path.join(tempfile.gettempdir(), "managed_json_sessions")
print(f"ManagedAgent + JSON File Persistence\nSession dir: {SESSION_DIR}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

store = DefaultSessionStore(session_dir=SESSION_DIR)
managed = ManagedAgent(
    provider="local", session_store=store,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="JSON Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My favourite city is Barcelona, Spain. I love the Sagrada Familia. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: I always stay at Hotel Arts in Barcelona. Confirm.")
print(f"Agent: {result2[:200]}...")

# ── Phase 2: Verify JSON files ──
print("\n=== Phase 2: JSON File Verification ===")
json_files = [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")]
print(f"Files: {json_files}")
for fname in json_files:
    with open(os.path.join(SESSION_DIR, fname), "r") as f:
        data = json.load(f)
    print(f"  {fname}: {len(data.get('messages', []))} messages")

# ── Phase 3: Destroy instance ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
session_id = saved_ids["session_id"]
print(f"Saved IDs: {saved_ids}")
del agent, managed, store
print("Agent destroyed.\n")

# ── Phase 4: Resume — no config needed ──
print("=== Phase 4: Resume Session ===")
store2 = DefaultSessionStore(session_dir=SESSION_DIR)
managed2 = ManagedAgent(provider="local", session_store=store2)
managed2.resume_session(session_id)
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("What is my favourite city, landmark, and hotel?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Barcelona'": "barcelona" in r,
    "Remembers 'Sagrada Familia'": "sagrada" in r,
    "Remembers 'Hotel Arts'": "hotel arts" in r or "arts" in r,
    "Session ID continuity": managed2.session_id == session_id,
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

shutil.rmtree(SESSION_DIR)
print(f"\n{'PASS' if all_passed else 'FAIL'}: JSON File ManagedAgent persistence test")
