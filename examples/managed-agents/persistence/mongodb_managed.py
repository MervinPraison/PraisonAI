#!/usr/bin/env python3
"""
ManagedAgent + MongoDB Persistence — Real conversation with session resume.

MongoDB stores state metadata; SQLite stores conversation history.

Prerequisites:
    pip install praisonai praisonaiagents pymongo
    export OPENAI_API_KEY="sk-..."
    # MongoDB running on localhost:27017
"""

import os
import sys
import tempfile

import pymongo

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
SQLITE_PATH = os.path.join(tempfile.gettempdir(), "managed_mongo_conv.db")
print(f"ManagedAgent + MongoDB Persistence\nMongoDB: {MONGO_URL}\nSQLite: {SQLITE_PATH}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=SQLITE_PATH)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="MongoDB Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My favourite book is 'Dune' by Frank Herbert, published 1965. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: 'Dune Messiah' is my second favourite. Confirm.")
print(f"Agent: {result2[:200]}...")

# Store session metadata into MongoDB for verification
mongo_client = pymongo.MongoClient(MONGO_URL)
mongo_col = mongo_client["praisonai_managed"]["sessions"]
state_doc = {
    "_id": managed.session_id,
    "agent_id": managed.agent_id,
    "total_input_tokens": managed.total_input_tokens,
}
mongo_col.replace_one({"_id": managed.session_id}, state_doc, upsert=True)

# ── Phase 2: MongoDB Verification ──
print("\n=== Phase 2: MongoDB Verification ===")
doc = mongo_col.find_one({"_id": managed.session_id})
print(f"  Session in MongoDB: {doc['_id']}" if doc else "  WARNING: not found")

# ── Phase 3: Destroy instance ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
session_id = saved_ids["session_id"]
print(f"Saved IDs: {saved_ids}")
del agent, managed, db
print("Agent destroyed.\n")

# ── Phase 4: Resume — no config needed ──
print("=== Phase 4: Resume Session ===")
db2 = DB(database_url=SQLITE_PATH)
managed2 = ManagedAgent(provider="local", db=db2)
managed2.resume_session(session_id)
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("What is my favourite book, author, year, and second favourite?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Dune'": "dune" in r,
    "Remembers 'Herbert'": "herbert" in r,
    "Remembers '1965'": "1965" in r,
    "Remembers 'Messiah'": "messiah" in r,
    "Session ID continuity": managed2.session_id == session_id,
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

mongo_col.delete_one({"_id": session_id})
mongo_client.close()
os.unlink(SQLITE_PATH)
print(f"\n{'PASS' if all_passed else 'FAIL'}: MongoDB ManagedAgent persistence test")
