#!/usr/bin/env python3
"""
ManagedAgent + PostgreSQL Persistence — Real conversation with session resume.

Prerequisites:
    pip install praisonai praisonaiagents psycopg2-binary
    export OPENAI_API_KEY="sk-..."
    # PostgreSQL running on localhost:5432
"""

import os
import sys

import psycopg2

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

PG_URL = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
print(f"ManagedAgent + PostgreSQL Persistence\nDB: {PG_URL}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=PG_URL)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="PG Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My favourite language is Rust, 3 years experience. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: I'm building a web crawler with the reqwest crate. Confirm.")
print(f"Agent: {result2[:200]}...")

# ── Phase 2: Direct PostgreSQL Verification ──
print("\n=== Phase 2: PostgreSQL Verification ===")
conn = psycopg2.connect(PG_URL)
cursor = conn.cursor()
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name LIKE '%message%'
""")
msg_tables = [r[0] for r in cursor.fetchall()]
print(f"Message tables: {msg_tables}")
for t in msg_tables:
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {cursor.fetchone()[0]} rows")
conn.close()

# ── Phase 3: Destroy instance ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
print(f"Saved IDs: {saved_ids}")
del agent, managed, db
print("Agent destroyed.\n")

# ── Phase 4: Resume — no config needed ──
print("=== Phase 4: Resume Session ===")
db2 = DB(database_url=PG_URL)
managed2 = ManagedAgent(provider="local", db=db2)
managed2.resume_session(saved_ids["session_id"])
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("What is my favourite language, experience, and what am I building?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Rust'": "rust" in r,
    "Remembers '3 years'": "3" in r and "year" in r,
    "Remembers 'crawler'": "crawler" in r or "crawl" in r,
    "Remembers 'reqwest'": "reqwest" in r,
    "Session ID continuity": managed2.session_id == saved_ids["session_id"],
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

print(f"\n{'PASS' if all_passed else 'FAIL'}: PostgreSQL ManagedAgent persistence test")
