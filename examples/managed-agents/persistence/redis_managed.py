#!/usr/bin/env python3
"""
ManagedAgent + Redis Persistence — Real conversation with session resume.

Redis stores state/metadata; SQLite stores conversation history.

Prerequisites:
    pip install praisonai praisonaiagents redis
    export OPENAI_API_KEY="sk-..."
    # Redis running on localhost:6379
"""

import os
import sys
import tempfile

import redis as redis_lib

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

REDIS_URL = os.getenv("REDIS_URL", "redis://:myredissecret@localhost:6379/0")
SQLITE_PATH = os.path.join(tempfile.gettempdir(), "managed_redis_conv.db")
print(f"ManagedAgent + Redis Persistence\nRedis: {REDIS_URL}\nSQLite: {SQLITE_PATH}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=SQLITE_PATH, state_url=REDIS_URL)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="Redis Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My cat Luna is a Siamese who loves tuna treats. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: Luna was adopted from a shelter in Portland, Oregon. Confirm.")
print(f"Agent: {result2[:200]}...")

# ── Phase 2: Direct Redis Verification ──
print("\n=== Phase 2: Redis Verification ===")
rc = redis_lib.Redis(host="localhost", port=6379, password="myredissecret", decode_responses=True)
all_keys = rc.keys("*")
print(f"Total Redis keys: {len(all_keys)}")

# ── Phase 3: Destroy instance ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
print(f"Saved IDs: {saved_ids}")
del agent, managed, db
print("Agent destroyed.\n")

# ── Phase 4: Resume — no config needed ──
print("=== Phase 4: Resume Session ===")
db2 = DB(database_url=SQLITE_PATH, state_url=REDIS_URL)
managed2 = ManagedAgent(provider="local", db=db2)
managed2.resume_session(saved_ids["session_id"])
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("What is my cat's name, breed, favourite treat, and adoption city?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Luna'": "luna" in r,
    "Remembers 'Siamese'": "siamese" in r,
    "Remembers 'tuna'": "tuna" in r,
    "Remembers 'Portland'": "portland" in r,
    "Session ID continuity": managed2.session_id == saved_ids["session_id"],
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

os.unlink(SQLITE_PATH)
print(f"\n{'PASS' if all_passed else 'FAIL'}: Redis ManagedAgent persistence test")
