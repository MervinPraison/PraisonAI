"""
MySQL ConversationStore — Full Persistence Example

Demonstrates:
  - Creating a MySQL ConversationStore
  - Creating sessions, adding messages
  - Direct SQL verification that data is in MySQL
  - Session resume after simulated restart

Requirements:
    pip install praisonai mysql-connector-python
    Docker: MySQL on localhost:3307 (user=root, password=praisontest, database=praisonai)

Run:
    python mysql_conversation_store.py
"""

import uuid
import mysql.connector
from praisonai.persistence.conversation.mysql import MySQLConversationStore
from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

MYSQL_HOST = "localhost"
MYSQL_PORT = 3307
MYSQL_USER = "root"
MYSQL_PASSWORD = "praisontest"
MYSQL_DB = "praisonai"
TABLE_PREFIX = f"example_{uuid.uuid4().hex[:6]}_"

print(f"MySQL: {MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
print(f"Table prefix: {TABLE_PREFIX}\n")

store = MySQLConversationStore(
    host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
    password=MYSQL_PASSWORD, database=MYSQL_DB, table_prefix=TABLE_PREFIX,
)
SESSION_ID = f"mysql-demo-{uuid.uuid4().hex[:8]}"

# --- Phase 1: Create session and add messages ---
print("=== Phase 1: Create Session & Add Messages ===")
session = ConversationSession(
    session_id=SESSION_ID,
    agent_id="mysql_demo_agent",
    name="MySQL Demo",
    metadata={"agent_version": 7, "model": "gpt-4o-mini"},
)
store.create_session(session)

messages = [
    ("user", "What makes MySQL popular?"),
    ("assistant", "MySQL is popular for its speed, reliability, and ease of use in web applications."),
    ("user", "What about scalability?"),
    ("assistant", "MySQL supports replication, sharding, and clustering for horizontal scalability."),
]

for role, content in messages:
    msg = ConversationMessage(session_id=SESSION_ID, role=role, content=content)
    store.add_message(SESSION_ID, msg)
    print(f"  Added [{role}]: {content[:60]}")

print()

# --- Phase 2: Verify data ---
print("=== Phase 2: Verify Data in MySQL ===")
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
conn = mysql.connector.connect(
    host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
    password=MYSQL_PASSWORD, database=MYSQL_DB,
)
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM {TABLE_PREFIX}messages WHERE session_id = %s", (SESSION_ID,))
count = cur.fetchone()[0]
print(f"  Raw SQL message count: {count}")
assert count == 4, f"Expected 4, got {count}"

cur.execute(f"SELECT agent_id FROM {TABLE_PREFIX}sessions WHERE session_id = %s", (SESSION_ID,))
agent_id = cur.fetchone()[0]
print(f"  Raw SQL agent_id: {agent_id}")
assert agent_id == "mysql_demo_agent"
conn.close()

print()

# --- Phase 4: Session Resume ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
store.close()

store2 = MySQLConversationStore(
    host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
    password=MYSQL_PASSWORD, database=MYSQL_DB, table_prefix=TABLE_PREFIX,
)
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
conn = mysql.connector.connect(
    host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
    password=MYSQL_PASSWORD, database=MYSQL_DB,
)
cur = conn.cursor()
cur.execute(f"DROP TABLE IF EXISTS {TABLE_PREFIX}messages")
cur.execute(f"DROP TABLE IF EXISTS {TABLE_PREFIX}sessions")
conn.commit()
conn.close()
print("  Tables dropped.")

print("\n✅ MySQL ConversationStore — All tests passed!")
