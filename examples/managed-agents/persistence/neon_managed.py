"""
Neon Serverless PostgreSQL Persistence Example.

Neon auto-idles after inactivity — you only pay when active.
The PraisonAI adapter auto-handles cold-start retries and SSL.

Setup:
  1. Create free Neon project at https://neon.tech
  2. Copy connection string from dashboard
  3. Set env var: export NEON_DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/dbname?sslmode=require"
  4. pip install praisonai[neon]
"""

import os
from praisonaiagents import Agent

# Option 1: Use NEON_DATABASE_URL env var (recommended)
agent = Agent(
    name="Neon Agent",
    instructions="You are a helpful assistant.",
    db={"database_url": os.getenv("NEON_DATABASE_URL")},
    session_id="neon-demo-session",
)

# Option 2: Direct URL
# agent = Agent(
#     name="Neon Agent",
#     instructions="You are a helpful assistant.",
#     db={"database_url": "postgresql://user:pass@ep-xxx.neon.tech/dbname?sslmode=require"},
#     session_id="neon-demo-session",
# )

result = agent.start("What is serverless PostgreSQL? Explain in 2 sentences.")
print(result)
