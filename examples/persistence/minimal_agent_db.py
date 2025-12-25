"""
Minimal Agent with Database Persistence

This is the simplest way to add persistence to your agent.
Messages, runs, and traces are automatically saved.

Run:
    python minimal_agent_db.py

Expected output:
    - Agent responds to your question
    - Data is persisted to PostgreSQL
    - Session can be resumed later with same session_id
"""

from praisonaiagents import Agent, db

# Create database connection (PostgreSQL + Redis)
my_db = db(
    database_url="postgresql://postgres:praison123@localhost:5432/praisonai",
    state_url="redis://localhost:6379"  # Optional: for state/tracing
)

# Create agent with persistence
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Be concise.",
    db=my_db,
    # session_id is optional - defaults to per-hour ID (YYYYMMDDHH-hash)
    # Set explicitly for session continuity across runs:
    session_id="my-persistent-session"
)

# Chat - messages are automatically persisted
response = agent.chat("What is the capital of France?")
print(f"Response: {response}")

# Verify persistence
data = my_db.export_session("my-persistent-session")
print(f"\nMessages stored: {len(data.get('messages', []))}")

# Clean up
my_db.close()
