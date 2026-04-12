"""
Redis StateStore — Full Persistence Example

Demonstrates:
  - Creating a Redis StateStore
  - Key-value operations (get/set/delete/exists)
  - JSON state persistence (agent metadata, usage tokens)
  - Hash operations for structured data
  - Session resume: simulate restart, recover state

Requirements:
    pip install praisonai redis
    Docker: Redis on localhost:6379 (password=myredissecret)

Run:
    python redis_state_store.py
"""

import uuid
import redis as redis_lib
from praisonai.persistence.state.redis import RedisStateStore

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = "myredissecret"
PREFIX = f"example_{uuid.uuid4().hex[:6]}:"

print(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
print(f"Key prefix: {PREFIX}\n")

store = RedisStateStore(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, prefix=PREFIX,
)

# --- Phase 1: Basic key-value operations ---
print("=== Phase 1: Basic Key-Value Operations ===")
store.set("agent_id", "redis_demo_agent_001")
store.set("model", "gpt-4o-mini")
store.set("counter", "42")

print(f"  agent_id: {store.get('agent_id')}")
print(f"  model: {store.get('model')}")
print(f"  counter: {store.get('counter')}")
print(f"  exists('agent_id'): {store.exists('agent_id')}")
print(f"  exists('missing'): {store.exists('missing')}")

print()

# --- Phase 2: JSON state persistence ---
print("=== Phase 2: JSON State Persistence ===")
managed_state = {
    "agent_id": "redis_demo_agent_001",
    "agent_version": 3,
    "environment_id": "env_local_001",
    "total_input_tokens": 1500,
    "total_output_tokens": 600,
    "compute_instance_id": "docker_redis_demo",
    "session_history": [
        {"id": "session_001", "status": "completed", "title": "Weather chat"},
        {"id": "session_002", "status": "idle", "title": "Code review"},
    ],
}

store.set_json("managed_state", managed_state)
recovered = store.get_json("managed_state")

print(f"  agent_id: {recovered['agent_id']}")
print(f"  agent_version: {recovered['agent_version']}")
print(f"  total_input_tokens: {recovered['total_input_tokens']}")
print(f"  total_output_tokens: {recovered['total_output_tokens']}")
print(f"  compute_instance_id: {recovered['compute_instance_id']}")
print(f"  session_history count: {len(recovered['session_history'])}")

assert recovered["agent_id"] == "redis_demo_agent_001"
assert recovered["total_input_tokens"] == 1500
assert recovered["compute_instance_id"] == "docker_redis_demo"

print()

# --- Phase 3: Hash operations ---
print("=== Phase 3: Hash Operations ===")
store.hset("agent_meta", "version", "5")
store.hset("agent_meta", "env_id", "env_abc")
store.hset("agent_meta", "model", "gpt-4o")

print(f"  version: {store.hget('agent_meta', 'version')}")
all_meta = store.hgetall("agent_meta")
print(f"  all fields: {all_meta}")

print()

# --- Phase 4: Session Resume (Simulating Restart) ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
store.close()

# New store instance (simulating process restart)
store2 = RedisStateStore(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, prefix=PREFIX,
)

# Recover state
recovered2 = store2.get_json("managed_state")
assert recovered2 is not None, "State not found after restart!"
print(f"  Recovered agent_id: {recovered2['agent_id']}")
print(f"  Recovered tokens: in={recovered2['total_input_tokens']}, out={recovered2['total_output_tokens']}")
print(f"  Recovered compute: {recovered2['compute_instance_id']}")
print(f"  Recovered sessions: {len(recovered2['session_history'])}")

# Update state (simulate more work)
recovered2["total_input_tokens"] += 500
recovered2["total_output_tokens"] += 200
store2.set_json("managed_state", recovered2)

final = store2.get_json("managed_state")
print(f"  Updated tokens: in={final['total_input_tokens']}, out={final['total_output_tokens']}")
assert final["total_input_tokens"] == 2000
assert final["total_output_tokens"] == 800

store2.close()

# --- Cleanup ---
print("\n=== Cleanup ===")
r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
for key in r.keys(f"{PREFIX}*"):
    r.delete(key)
r.close()
print("  Keys deleted.")

print("\n✅ Redis StateStore — All tests passed!")
