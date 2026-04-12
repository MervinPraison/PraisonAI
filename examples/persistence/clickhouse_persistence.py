"""
ClickHouse — Persistence Example

Demonstrates:
  - Connecting to ClickHouse
  - Creating tables for agent state
  - Writing and reading agent metadata
  - JSON state storage and retrieval
  - Session resume after simulated restart

Requirements:
    pip install clickhouse-connect
    Docker: ClickHouse on localhost:8123 (user=clickhouse, password=clickhouse)

Run:
    python clickhouse_persistence.py
"""

import json
import uuid
import clickhouse_connect

CH_HOST = "localhost"
CH_PORT = 8123
CH_USER = "clickhouse"
CH_PASSWORD = "clickhouse"

print(f"ClickHouse: {CH_HOST}:{CH_PORT}\n")

client = clickhouse_connect.get_client(
    host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD,
)

TABLE_SESSIONS = f"praison_sessions_{uuid.uuid4().hex[:8]}"
TABLE_STATE = f"praison_state_{uuid.uuid4().hex[:8]}"

# --- Phase 1: Create tables and insert session data ---
print("=== Phase 1: Create Tables & Insert Sessions ===")
client.command(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_SESSIONS} (
        session_id String,
        agent_id String,
        agent_version UInt32,
        total_input_tokens UInt64,
        total_output_tokens UInt64,
        model String,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY session_id
""")

sessions = [
    ["session_ch_001", "agent_demo_001", 3, 500, 200, "gpt-4o"],
    ["session_ch_002", "agent_demo_002", 1, 1000, 400, "gpt-4o-mini"],
    ["session_ch_003", "agent_demo_001", 3, 750, 300, "gpt-4o"],
]

client.insert(
    TABLE_SESSIONS, sessions,
    column_names=["session_id", "agent_id", "agent_version", "total_input_tokens", "total_output_tokens", "model"],
)

for s in sessions:
    print(f"  Inserted: {s[0]} (agent={s[1]}, tokens_in={s[3]})")

print()

# --- Phase 2: Query and verify ---
print("=== Phase 2: Query & Verify ===")
result = client.query(f"SELECT * FROM {TABLE_SESSIONS} ORDER BY session_id")
print(f"  Total sessions: {len(result.result_rows)}")
for row in result.result_rows:
    print(f"    {row[0]}: agent={row[1]}, v{row[2]}, tokens_in={row[3]}, model={row[5]}")

assert len(result.result_rows) == 3
assert result.result_rows[0][0] == "session_ch_001"

# Aggregate query
agg = client.query(f"SELECT agent_id, SUM(total_input_tokens) as total_in FROM {TABLE_SESSIONS} GROUP BY agent_id ORDER BY agent_id")
print("\n  Tokens by agent:")
for row in agg.result_rows:
    print(f"    {row[0]}: {row[1]} input tokens")

print()

# --- Phase 3: JSON state storage ---
print("=== Phase 3: JSON State Storage ===")
client.command(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_STATE} (
        session_id String,
        state_json String,
        updated_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY session_id
""")

state = {
    "agent_id": "agent_demo_001",
    "agent_version": 3,
    "environment_id": "env_ch_001",
    "total_input_tokens": 2000,
    "total_output_tokens": 800,
    "compute_instance_id": "flyio_ch_001",
    "session_history": [
        {"id": "session_ch_001", "status": "completed"},
        {"id": "session_ch_003", "status": "idle"},
    ],
}

client.insert(
    TABLE_STATE,
    [["session_ch_001", json.dumps(state)]],
    column_names=["session_id", "state_json"],
)
print("  Stored JSON state for session_ch_001")

# Retrieve
result = client.query(f"SELECT state_json FROM {TABLE_STATE} WHERE session_id = 'session_ch_001'")
recovered = json.loads(result.result_rows[0][0])
print(f"  Recovered agent_id: {recovered['agent_id']}")
print(f"  Recovered tokens: in={recovered['total_input_tokens']}, out={recovered['total_output_tokens']}")
print(f"  Recovered compute: {recovered['compute_instance_id']}")
assert recovered["total_input_tokens"] == 2000

print()

# --- Phase 4: Session Resume ---
print("=== Phase 4: Session Resume (Simulating Restart) ===")
client.close()

client2 = clickhouse_connect.get_client(
    host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD,
)

result2 = client2.query(f"SELECT state_json FROM {TABLE_STATE} WHERE session_id = 'session_ch_001'")
assert len(result2.result_rows) > 0, "State not found after restart!"
recovered2 = json.loads(result2.result_rows[0][0])
print(f"  Recovered after restart: agent={recovered2['agent_id']}, tokens_in={recovered2['total_input_tokens']}")

# Update state
recovered2["total_input_tokens"] += 500
client2.insert(
    TABLE_STATE,
    [["session_ch_001", json.dumps(recovered2)]],
    column_names=["session_id", "state_json"],
)
print(f"  Updated tokens_in: {recovered2['total_input_tokens']}")  # noqa: F541

# --- Cleanup ---
print("\n=== Cleanup ===")
client2.command(f"DROP TABLE IF EXISTS {TABLE_SESSIONS}")
client2.command(f"DROP TABLE IF EXISTS {TABLE_STATE}")
client2.close()
print("  Tables dropped.")

print("\n✅ ClickHouse Persistence — All tests passed!")
