"""
MongoDB StateStore — Full Persistence Example

Demonstrates:
  - Creating a MongoDB StateStore
  - Key-value operations (get/set/delete/exists)
  - Complex state persistence (agent metadata, usage tokens)
  - Direct MongoDB verification
  - Session resume after simulated restart

Requirements:
    pip install praisonai pymongo
    Docker: MongoDB on localhost:27017 (no auth)

Run:
    python mongodb_state_store.py
"""

import uuid
import pymongo
from praisonai.persistence.state.mongodb import MongoDBStateStore

MONGO_URL = "mongodb://localhost:27017"
DATABASE = "praisonai_example"
COLLECTION = f"state_{uuid.uuid4().hex[:8]}"

print(f"MongoDB: {MONGO_URL}")
print(f"Database: {DATABASE}, Collection: {COLLECTION}\n")

store = MongoDBStateStore(url=MONGO_URL, database=DATABASE, collection=COLLECTION)

# --- Phase 1: Basic key-value operations ---
print("=== Phase 1: Basic Key-Value Operations ===")
store.set("agent_id", "mongo_demo_agent_001")
store.set("model", "gpt-4o-mini")
store.set("counter", 42)

print(f"  agent_id: {store.get('agent_id')}")
print(f"  model: {store.get('model')}")
print(f"  counter: {store.get('counter')}")
print(f"  exists('agent_id'): {store.exists('agent_id')}")
print(f"  exists('missing'): {store.exists('missing')}")

assert store.get("agent_id") == "mongo_demo_agent_001"
assert store.get("counter") == 42

print()

# --- Phase 2: Complex state persistence ---
print("=== Phase 2: Complex State Persistence ===")
managed_state = {
    "agent_id": "mongo_demo_agent_001",
    "agent_version": 4,
    "environment_id": "env_mongo_001",
    "total_input_tokens": 800,
    "total_output_tokens": 300,
    "compute_instance_id": "e2b_mongo_demo",
    "session_history": [
        {"id": "session_m1", "status": "completed"},
        {"id": "session_m2", "status": "idle"},
    ],
}

store.set("managed_state", managed_state)
recovered = store.get("managed_state")

print(f"  agent_id: {recovered['agent_id']}")
print(f"  agent_version: {recovered['agent_version']}")
print(f"  total_input_tokens: {recovered['total_input_tokens']}")
print(f"  compute_instance_id: {recovered['compute_instance_id']}")
print(f"  session_history count: {len(recovered['session_history'])}")

assert recovered["agent_id"] == "mongo_demo_agent_001"
assert recovered["total_input_tokens"] == 800

print()

# --- Phase 3: Direct MongoDB Verification ---
print("=== Phase 3: Direct MongoDB Verification ===")
client = pymongo.MongoClient(MONGO_URL)
doc = client[DATABASE][COLLECTION].find_one({"_id": "managed_state"})
print(f"  Raw doc _id: {doc['_id']}")
print(f"  Raw doc value.agent_id: {doc['value']['agent_id']}")
print(f"  Raw doc value.total_input_tokens: {doc['value']['total_input_tokens']}")
assert doc["value"]["compute_instance_id"] == "e2b_mongo_demo"
client.close()

print()

# --- Phase 4: Session Resume ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
store.close()

store2 = MongoDBStateStore(url=MONGO_URL, database=DATABASE, collection=COLLECTION)

recovered2 = store2.get("managed_state")
assert recovered2 is not None, "State not found after restart!"
print(f"  Recovered agent_id: {recovered2['agent_id']}")
print(f"  Recovered tokens: in={recovered2['total_input_tokens']}, out={recovered2['total_output_tokens']}")
print(f"  Recovered compute: {recovered2['compute_instance_id']}")

# Update
recovered2["total_input_tokens"] += 400
store2.set("managed_state", recovered2)
final = store2.get("managed_state")
print(f"  Updated input_tokens: {final['total_input_tokens']}")
assert final["total_input_tokens"] == 1200

# Delete test
store2.delete("counter")
assert not store2.exists("counter")
print("  Delete verified: counter removed")

store2.close()

# --- Cleanup ---
print("\n=== Cleanup ===")
client = pymongo.MongoClient(MONGO_URL)
client[DATABASE].drop_collection(COLLECTION)
client.close()
print("  Collection dropped.")

print("\n✅ MongoDB StateStore — All tests passed!")
