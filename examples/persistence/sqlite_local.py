"""
SQLite Local Database

Use SQLite for simple local persistence without external services.

Run:
    python sqlite_local.py

Expected output:
    - Agent responds
    - Data persisted to local SQLite file
"""

from praisonaiagents import Agent, db
import tempfile
import os

# Create SQLite database (local file)
db_path = os.path.join(tempfile.gettempdir(), "my_agent.db")
my_db = db.SQLiteDB(path=db_path)

print(f"Database: {db_path}")

# Create agent
agent = Agent(
    name="LocalBot",
    instructions="You are a helpful assistant.",
    db=my_db,
    session_id="local-session"
)

# Chat
response = agent.chat("Hello! What can you help me with?")
print(f"Response: {response}")

# Verify
data = my_db.export_session("local-session")
print(f"\nMessages stored: {len(data.get('messages', []))}")

my_db.close()
print("✅ Done")
