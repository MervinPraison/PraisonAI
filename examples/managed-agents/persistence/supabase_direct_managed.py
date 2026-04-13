"""
Supabase Direct PostgreSQL Persistence Example.

Supabase offers two connection modes:
  1. REST API (via supabase-py) — set SUPABASE_URL + SUPABASE_KEY
  2. Direct PostgreSQL (via psycopg2) — use Postgres connection string

This example uses direct PostgreSQL mode with auto-retry for paused projects.

Setup:
  1. Create free Supabase project at https://supabase.com
  2. Go to Settings > Database > Connection string (URI)
  3. Set env var: export SUPABASE_DATABASE_URL="postgresql://postgres.xxx:[pass]@xxx.pooler.supabase.com:6543/postgres"
  4. pip install praisonai[postgresql]
"""

import os
from praisonaiagents import Agent

agent = Agent(
    name="Supabase Agent",
    instructions="You are a helpful assistant.",
    db={"database_url": os.getenv("SUPABASE_DATABASE_URL")},
    session_id="supabase-demo-session",
)

result = agent.start("What is Supabase? Explain in 2 sentences.")
print(result)
