#!/usr/bin/env python3
"""
ManagedAgent + SQLite Persistence — Real conversation with session resume.

Prerequisites:
    pip install praisonai praisonaiagents
    export OPENAI_API_KEY="sk-..."
"""

import os
import sqlite3
import sys
import tempfile

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

DB_PATH = os.path.join(tempfile.gettempdir(), "managed_sqlite_test.db")
print(f"ManagedAgent + SQLite Persistence\nDB: {DB_PATH}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=DB_PATH)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="SQLite Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)

agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My dog's name is Biscuit, a golden retriever. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: Biscuit's favourite toy is a blue squeaky ball. Confirm.")
print(f"Agent: {result2[:200]}...")

# ── Phase 2: Verify SQLite directly ──
print("\n=== Phase 2: SQLite Verification ===")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print(f"Tables: {tables}")
for t in tables:
    if "message" in t.lower():
        cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
        print(f"  {t}: {cursor.fetchone()[0]} rows")
conn.close()

# ── Phase 3: Destroy instance (simulate idle) ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
print(f"Saved IDs: {saved_ids}")
del agent, managed, db
print("Agent destroyed.\n")

# ── Phase 4: Resume — no config needed, restored from DB ──
print("=== Phase 4: Resume Session ===")
db2 = DB(database_url=DB_PATH)
managed2 = ManagedAgent(provider="local", db=db2)
managed2.resume_session(saved_ids["session_id"])
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("What is my dog's name, breed, and favourite toy?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Biscuit'": "biscuit" in r,
    "Remembers 'golden retriever'": "golden retriever" in r,
    "Remembers toy": "blue" in r or "squeaky" in r,
    "Session ID continuity": managed2.session_id == saved_ids["session_id"],
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

os.unlink(DB_PATH)
print(f"\n{'PASS' if all_passed else 'FAIL'}: SQLite ManagedAgent persistence test")
