"""
Redis State Store

Use Redis for state management, tracing, and caching.

Run:
    python redis_state.py

Expected output:
    - State operations (set/get/delete)
    - Tracing operations
"""

from praisonaiagents import db

# Create Redis-only database (for state/tracing)
redis_db = db.RedisDB(host="localhost", port=6379)

print("=== Redis State Store ===")

# Test state operations
print("\n1. State Operations:")
redis_db._init_stores()  # Initialize stores

# Set a value
redis_db._state_store.set("user:123:preferences", {
    "theme": "dark",
    "language": "en"
})
print("   Set user preferences")

# Get the value
prefs = redis_db._state_store.get("user:123:preferences")
print(f"   Got preferences: {prefs}")

# Set with TTL (expires in 60 seconds)
redis_db._state_store.set("temp:token", "abc123", ttl=60)
print("   Set temporary token (60s TTL)")

# Delete
redis_db._state_store.delete("user:123:preferences")
print("   Deleted preferences")

# Test tracing
print("\n2. Tracing Operations:")

# Start a trace
trace_id = "trace-example-001"
redis_db.on_trace_start(
    trace_id=trace_id,
    session_id="example-session",
    agent_name="ExampleAgent",
    metadata={"purpose": "demo"}
)
print(f"   Started trace: {trace_id}")

# Add spans
span_id = "span-llm-001"
redis_db.on_span_start(
    span_id=span_id,
    trace_id=trace_id,
    name="llm_call",
    attributes={"model": "gpt-4", "temperature": 0.7}
)
print(f"   Started span: {span_id}")

redis_db.on_span_end(
    span_id=span_id,
    status="ok",
    attributes={"tokens": 150, "latency_ms": 450}
)
print(f"   Ended span: {span_id}")

# End trace
redis_db.on_trace_end(
    trace_id=trace_id,
    status="ok",
    metadata={"total_spans": 1}
)
print(f"   Ended trace: {trace_id}")

redis_db.close()
print("\n✅ Done")
