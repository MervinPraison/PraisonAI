#!/usr/bin/env python3
"""
ManagedAgent + MySQL Persistence — Real conversation with session resume.

Prerequisites:
    pip install praisonai praisonaiagents mysql-connector-python
    export OPENAI_API_KEY="sk-..."
    # MySQL running on localhost:3307
"""

import os
import sys

import mysql.connector

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

MYSQL_URL = os.getenv("MYSQL_URL", "mysql://root:praisontest@localhost:3307/praisonai")
print(f"ManagedAgent + MySQL Persistence\nDB: {MYSQL_URL}\n")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=MYSQL_URL)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="MySQL Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: I live in Tokyo, Japan and love ramen from Ichiran. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: I work as a machine learning engineer at a robotics company. Confirm.")
print(f"Agent: {result2[:200]}...")

# ── Phase 2: Direct MySQL Verification ──
print("\n=== Phase 2: MySQL Verification ===")
conn = mysql.connector.connect(host="localhost", port=3307, user="root", password="praisontest", database="praisonai")
cursor = conn.cursor()
cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='praisonai' AND table_name LIKE '%message%'")
msg_tables = [r[0] for r in cursor.fetchall()]
print(f"Message tables: {msg_tables}")
for t in msg_tables:
    cursor.execute(f"SELECT COUNT(*) FROM `{t}`")
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
db2 = DB(database_url=MYSQL_URL)
managed2 = ManagedAgent(provider="local", db=db2)
managed2.resume_session(saved_ids["session_id"])
print(f"Resumed session: {managed2.session_id}")

agent2 = Agent(name="User", backend=managed2)
result3 = agent2.run("Where do I live, what's my favourite food, and what do I do for work?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Tokyo'": "tokyo" in r,
    "Remembers 'ramen'": "ramen" in r,
    "Remembers 'Ichiran'": "ichiran" in r,
    "Remembers 'machine learning'": "machine learning" in r or "ml" in r,
    "Remembers 'robotics'": "robotic" in r,
    "Session ID continuity": managed2.session_id == saved_ids["session_id"],
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

print(f"\n{'PASS' if all_passed else 'FAIL'}: MySQL ManagedAgent persistence test")
