"""
JSON File DefaultSessionStore — Full Persistence Example

Demonstrates:
  - Creating a DefaultSessionStore (JSON file-backed)
  - Adding messages and metadata
  - Verifying data on disk
  - Session resume after simulated restart
  - Full managed agent state roundtrip (7 data categories)

Requirements:
    pip install praisonaiagents

Run:
    python json_file_session_store.py
"""

import json
import os
import shutil
import tempfile
import uuid
from praisonaiagents.session.store import DefaultSessionStore

# --- Setup ---
session_dir = os.path.join(tempfile.gettempdir(), f"praison_json_example_{uuid.uuid4().hex[:6]}")
os.makedirs(session_dir, exist_ok=True)
print(f"Session directory: {session_dir}\n")

store = DefaultSessionStore(session_dir=session_dir)
SESSION_ID = f"json-demo-{uuid.uuid4().hex[:8]}"

# --- Phase 1: Add messages ---
print("=== Phase 1: Add Messages ===")
messages = [
    ("user", "What is machine learning?"),
    ("assistant", "Machine learning is a subset of AI that enables systems to learn from data."),
    ("user", "Give me an example."),
    ("assistant", "Spam filters use ML to classify emails as spam or not spam."),
]

for role, content in messages:
    store.add_message(SESSION_ID, role, content)
    print(f"  Added [{role}]: {content[:60]}")

print()

# --- Phase 2: Store metadata (simulating managed agent state) ---
print("=== Phase 2: Store Metadata ===")
session = store.get_session(SESSION_ID)
session.metadata = {
    "agent_id": "json_demo_agent_001",
    "agent_version": 2,
    "environment_id": "env_local_json",
    "total_input_tokens": 450,
    "total_output_tokens": 180,
    "compute_instance_id": "local_json_demo",
    "session_history": [
        {"id": SESSION_ID, "status": "idle", "title": "ML chat"},
    ],
}
store._save_session(session)

print(f"  agent_id: {session.metadata['agent_id']}")
print(f"  tokens: in={session.metadata['total_input_tokens']}, out={session.metadata['total_output_tokens']}")
print(f"  compute: {session.metadata['compute_instance_id']}")

print()

# --- Phase 3: Verify on disk ---
print("=== Phase 3: Verify JSON File on Disk ===")
json_file = os.path.join(session_dir, f"{SESSION_ID}.json")
assert os.path.exists(json_file), f"JSON file not found: {json_file}"

with open(json_file) as f:
    data = json.load(f)

print(f"  File: {json_file}")
print(f"  Session ID: {data['session_id']}")
print(f"  Messages: {len(data.get('messages', []))}")
print(f"  Metadata agent_id: {data['metadata']['agent_id']}")
print(f"  Metadata tokens_in: {data['metadata']['total_input_tokens']}")

assert data["metadata"]["agent_id"] == "json_demo_agent_001"
assert data["metadata"]["total_input_tokens"] == 450
assert len(data["messages"]) == 4

print()

# --- Phase 4: Session Resume ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
del store

store2 = DefaultSessionStore(session_dir=session_dir)

# Verify session exists
assert store2.session_exists(SESSION_ID), "Session not found after restart!"

# Recover history
history = store2.get_chat_history(SESSION_ID)
print(f"  Recovered messages: {len(history)}")
assert len(history) == 4

# Recover metadata
session2 = store2.get_session(SESSION_ID)
meta = session2.metadata
print(f"  Recovered agent_id: {meta['agent_id']}")
print(f"  Recovered tokens: in={meta['total_input_tokens']}, out={meta['total_output_tokens']}")
print(f"  Recovered compute: {meta['compute_instance_id']}")
print(f"  Recovered session_history: {len(meta['session_history'])} entries")

assert meta["agent_id"] == "json_demo_agent_001"
assert meta["total_input_tokens"] == 450
assert meta["compute_instance_id"] == "local_json_demo"

# Continue conversation
store2.add_message(SESSION_ID, "user", "What about deep learning?")
store2.add_message(SESSION_ID, "assistant", "Deep learning uses neural networks with many layers.")
final_history = store2.get_chat_history(SESSION_ID)
print(f"  Messages after resume: {len(final_history)}")
assert len(final_history) == 6

# --- Cleanup ---
print("\n=== Cleanup ===")
shutil.rmtree(session_dir)
print("  Session directory removed.")

print("\n✅ JSON File DefaultSessionStore — All tests passed!")
