"""
SQLite ConversationStore — Full Persistence Example

Demonstrates:
  - Creating a SQLite ConversationStore
  - Creating sessions and adding messages
  - Verifying data is stored in the SQLite file
  - Session resume: destroy agent, restore from DB, verify state

Requirements:
    pip install praisonai

Run:
    python sqlite_conversation_store.py
"""

import os
import sqlite3
import tempfile
from praisonai.persistence.conversation.sqlite import SQLiteConversationStore
from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

# --- Setup ---
db_path = os.path.join(tempfile.gettempdir(), "praison_sqlite_example.db")
print(f"SQLite DB path: {db_path}\n")

store = SQLiteConversationStore(path=db_path)

SESSION_ID = "sqlite-demo-session-001"

# --- Phase 1: Create session and add messages ---
print("=== Phase 1: Create Session & Add Messages ===")
session = ConversationSession(
    session_id=SESSION_ID,
    agent_id="sqlite_demo_agent",
    name="SQLite Demo Session",
    metadata={"agent_version": 3, "environment": "local"},
)
store.create_session(session)

messages = [
    ("user", "Hello! What is the capital of France?"),
    ("assistant", "The capital of France is Paris."),
    ("user", "What about Germany?"),
    ("assistant", "The capital of Germany is Berlin."),
]

for role, content in messages:
    msg = ConversationMessage(session_id=SESSION_ID, role=role, content=content)
    store.add_message(SESSION_ID, msg)
    print(f"  Added [{role}]: {content[:50]}")

print()

# --- Phase 2: Verify data in DB ---
print("=== Phase 2: Verify Data in SQLite ===")
retrieved_session = store.get_session(SESSION_ID)
print(f"  Session ID: {retrieved_session.session_id}")
print(f"  Agent ID: {retrieved_session.agent_id}")
print(f"  Metadata: {retrieved_session.metadata}")

stored_messages = store.get_messages(SESSION_ID)
print(f"  Messages stored: {len(stored_messages)}")
for msg in stored_messages:
    print(f"    [{msg.role}] {msg.content[:60]}")

print()

# --- Phase 3: Session Resume ---
print("=== Phase 3: Session Resume (Simulating Restart) ===")
store.close()

# Reopen store from same file (simulating process restart)
store2 = SQLiteConversationStore(path=db_path)

# Verify session still exists
resumed_session = store2.get_session(SESSION_ID)
assert resumed_session is not None, "Session not found after restart!"
print(f"  Resumed session: {resumed_session.session_id}")
print(f"  Agent ID: {resumed_session.agent_id}")
print(f"  Metadata preserved: {resumed_session.metadata}")

# Verify messages
resumed_messages = store2.get_messages(SESSION_ID)
print(f"  Messages recovered: {len(resumed_messages)}")
assert len(resumed_messages) == 4, f"Expected 4 messages, got {len(resumed_messages)}"

# Continue the conversation
new_msg = ConversationMessage(session_id=SESSION_ID, role="user", content="What about Spain?")
store2.add_message(SESSION_ID, new_msg)
new_msg2 = ConversationMessage(session_id=SESSION_ID, role="assistant", content="The capital of Spain is Madrid.")
store2.add_message(SESSION_ID, new_msg2)

final_messages = store2.get_messages(SESSION_ID)
print(f"  Messages after resume: {len(final_messages)}")
assert len(final_messages) == 6

store2.close()

# --- Phase 4: Direct SQLite verification ---
print("\n=== Phase 4: Direct SQLite Verification ===")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM praison_messages WHERE session_id = ?", (SESSION_ID,))
count = cur.fetchone()[0]
print(f"  Raw SQL message count: {count}")
assert count == 6
conn.close()

# Cleanup
os.remove(db_path)
print("\n✅ SQLite ConversationStore — All tests passed!")
