"""
Turso/libSQL Persistence Example.

Turso provides SQLite-at-the-edge with automatic sync and scale-to-zero.

Setup:
  1. Create free Turso database at https://turso.tech
  2. Run: turso db tokens create <db-name>
  3. Set env vars:
     export TURSO_DATABASE_URL="libsql://mydb-user.turso.io"
     export TURSO_AUTH_TOKEN="eyJ..."
  4. pip install praisonai[turso]
"""

import os
from praisonaiagents import Agent

agent = Agent(
    name="Turso Agent",
    instructions="You are a helpful assistant.",
    db={
        "database_url": os.getenv("TURSO_DATABASE_URL"),
        "auth_token": os.getenv("TURSO_AUTH_TOKEN"),
    },
    session_id="turso-demo-session",
)

result = agent.start("What is edge computing? Explain in 2 sentences.")
print(result)
