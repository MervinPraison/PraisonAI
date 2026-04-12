#!/usr/bin/env python3
"""
ManagedAgent + ClickHouse Persistence — Real conversation with session resume.

ClickHouse stores analytics/state; SQLite stores conversation history.

Prerequisites:
    pip install praisonai praisonaiagents clickhouse-connect
    export OPENAI_API_KEY="sk-..."
    # ClickHouse running on localhost:8123
"""

import json
import os
import sys
import tempfile

import clickhouse_connect

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set.")

from praisonai import ManagedAgent, LocalManagedConfig, DB
from praisonaiagents import Agent

CH_HOST = os.getenv("CH_HOST", "localhost")
CH_PORT = int(os.getenv("CH_PORT", "8123"))
CH_USER = os.getenv("CH_USER", "clickhouse")
CH_PASSWORD = os.getenv("CH_PASSWORD", "clickhouse")
SQLITE_PATH = os.path.join(tempfile.gettempdir(), "managed_ch_conv.db")
print(f"ManagedAgent + ClickHouse Persistence\nCH: {CH_HOST}:{CH_PORT}\nSQLite: {SQLITE_PATH}\n")

# Setup ClickHouse table
client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
TABLE = "managed_agent_sessions"
client.command(f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        session_id String, agent_id String,
        input_tokens UInt64, output_tokens UInt64,
        state_json String, created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree() ORDER BY (session_id, created_at)
""")

# ── Phase 1: Create agent, teach facts ──
print("=== Phase 1: First Session ===")

db = DB(database_url=SQLITE_PATH)
managed = ManagedAgent(
    provider="local", db=db,
    config=LocalManagedConfig(
        model="gpt-4o-mini", name="ClickHouse Memory Agent",
        system="You are a helpful assistant. Remember all facts the user tells you.",
    ),
)
agent = Agent(name="User", backend=managed)

result1 = agent.run("Remember: My favourite movie is Interstellar by Christopher Nolan, 2014. Confirm.")
print(f"Agent: {result1[:200]}...")
print(f"Session ID: {managed.session_id}")

result2 = agent.run("Also remember: The Hans Zimmer soundtrack is my favourite film score. Confirm.")
print(f"Agent: {result2[:200]}...")

# Store to ClickHouse
session_id = managed.session_id
client.insert(TABLE, [[
    session_id, managed.agent_id or "",
    managed.total_input_tokens, managed.total_output_tokens,
    json.dumps({"environment_id": managed.environment_id}),
]], column_names=["session_id", "agent_id", "input_tokens", "output_tokens", "state_json"])

# ── Phase 2: ClickHouse Verification ──
print("\n=== Phase 2: ClickHouse Verification ===")
rows = client.query(f"SELECT session_id, agent_id FROM {TABLE} WHERE session_id=%(sid)s LIMIT 1", parameters={"sid": session_id})
for row in rows.result_rows:
    print(f"  session_id: {row[0]}, agent_id: {row[1]}")

# ── Phase 3: Destroy instance ──
print("\n=== Phase 3: Instance Goes Idle ===")
saved_ids = managed.save_ids()
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
result3 = agent2.run("What is my favourite movie, director, year, and soundtrack composer?")
print(f"Agent: {result3[:300]}...")

# ── Phase 5: Validate ──
print("\n=== Phase 5: Validation ===")
r = result3.lower()
checks = {
    "Remembers 'Interstellar'": "interstellar" in r,
    "Remembers 'Nolan'": "nolan" in r,
    "Remembers '2014'": "2014" in r,
    "Remembers 'Zimmer'": "zimmer" in r,
    "Session ID continuity": managed2.session_id == session_id,
}
all_passed = True
for check, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {check}")
    if not ok:
        all_passed = False

client.command(f"ALTER TABLE {TABLE} DELETE WHERE session_id = '{session_id}'")
client.close()
os.unlink(SQLITE_PATH)
print(f"\n{'PASS' if all_passed else 'FAIL'}: ClickHouse ManagedAgent persistence test")
