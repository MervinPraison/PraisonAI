"""
PostgreSQL ConversationStore — Full Persistence Example

Demonstrates:
  - Creating a PostgreSQL ConversationStore
  - Creating sessions, adding messages, storing metadata
  - Direct SQL verification that data is in PostgreSQL
  - Session resume after simulated restart

Requirements:
    pip install praisonai psycopg2-binary
    Docker: PostgreSQL on localhost:5432 (user=postgres, password=postgres)

Run:
    python postgres_conversation_store.py
"""

import uuid
import psycopg2
from praisonai.persistence.conversation.postgres import PostgresConversationStore
from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

PG_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
TABLE_PREFIX = f"example_{uuid.uuid4().hex[:6]}_"

print(f"PostgreSQL URL: {PG_URL}")
print(f"Table prefix: {TABLE_PREFIX}\n")

store = PostgresConversationStore(url=PG_URL, table_prefix=TABLE_PREFIX)
SESSION_ID = f"pg-demo-{uuid.uuid4().hex[:8]}"

# --- Phase 1: Create session and add messages ---
print("=== Phase 1: Create Session & Add Messages ===")
session = ConversationSession(
    session_id=SESSION_ID,
    agent_id="pg_demo_agent",
    name="PostgreSQL Demo",
    metadata={"agent_version": 5, "model": "gpt-4o"},
)
store.create_session(session)

messages = [
    ("user", "What are the benefits of PostgreSQL?"),
    ("assistant", "PostgreSQL offers ACID compliance, extensibility, JSON support, and excellent performance."),
    ("user", "How does it compare to MySQL?"),
    ("assistant", "PostgreSQL has better standards compliance and advanced features, while MySQL is simpler for basic use."),
]

for role, content in messages:
    msg = ConversationMessage(session_id=SESSION_ID, role=role, content=content)
    store.add_message(SESSION_ID, msg)
    print(f"  Added [{role}]: {content[:60]}")

print()

# --- Phase 2: Verify data in PostgreSQL ---
print("=== Phase 2: Verify Data in PostgreSQL ===")
retrieved = store.get_session(SESSION_ID)
print(f"  Session: {retrieved.session_id}")
print(f"  Agent ID: {retrieved.agent_id}")
print(f"  Metadata: {retrieved.metadata}")

stored = store.get_messages(SESSION_ID)
print(f"  Messages: {len(stored)}")
for msg in stored:
    print(f"    [{msg.role}] {msg.content[:70]}")

print()

# --- Phase 3: Direct SQL Verification ---
print("=== Phase 3: Direct SQL Verification ===")
conn = psycopg2.connect(PG_URL)
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM public.{TABLE_PREFIX}messages WHERE session_id = %s", (SESSION_ID,))
count = cur.fetchone()[0]
print(f"  Raw SQL message count: {count}")
assert count == 4, f"Expected 4, got {count}"

cur.execute(f"SELECT agent_id FROM public.{TABLE_PREFIX}sessions WHERE session_id = %s", (SESSION_ID,))
agent_id = cur.fetchone()[0]
print(f"  Raw SQL agent_id: {agent_id}")
assert agent_id == "pg_demo_agent"
conn.close()

print()

# --- Phase 4: Session Resume ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
store.close()

store2 = PostgresConversationStore(url=PG_URL, table_prefix=TABLE_PREFIX)
resumed = store2.get_session(SESSION_ID)
assert resumed is not None, "Session not found after restart!"
print(f"  Resumed session: {resumed.session_id}")
print(f"  Metadata preserved: {resumed.metadata}")

msgs = store2.get_messages(SESSION_ID)
print(f"  Messages recovered: {len(msgs)}")
assert len(msgs) == 4

# Continue
store2.add_message(SESSION_ID, ConversationMessage(session_id=SESSION_ID, role="user", content="Thanks!"))
store2.add_message(SESSION_ID, ConversationMessage(session_id=SESSION_ID, role="assistant", content="You're welcome!"))
final = store2.get_messages(SESSION_ID)
print(f"  Messages after resume: {len(final)}")
assert len(final) == 6

store2.close()

# --- Cleanup ---
print("\n=== Cleanup ===")
conn = psycopg2.connect(PG_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute(f"DROP TABLE IF EXISTS public.{TABLE_PREFIX}messages CASCADE")
cur.execute(f"DROP TABLE IF EXISTS public.{TABLE_PREFIX}sessions CASCADE")
conn.close()
print("  Tables dropped.")

print("\n✅ PostgreSQL ConversationStore — All tests passed!")
