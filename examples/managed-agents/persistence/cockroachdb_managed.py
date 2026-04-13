"""
CockroachDB Serverless Persistence Example.

CockroachDB Serverless provides distributed SQL with scale-to-zero.
Auto-handles serialization retries (error 40001) and SSL.

Setup:
  1. Create free CockroachDB Serverless cluster at https://cockroachlabs.cloud
  2. Copy connection string from dashboard
  3. Set env var: export COCKROACHDB_URL="postgresql://user:pass@xxx.cockroachlabs.cloud:26257/mydb?sslmode=verify-full"
  4. pip install praisonai[cockroachdb]
"""

import os
from praisonaiagents import Agent

agent = Agent(
    name="CockroachDB Agent",
    instructions="You are a helpful assistant.",
    db={"database_url": os.getenv("COCKROACHDB_URL")},
    session_id="crdb-demo-session",
)

result = agent.start("What is distributed SQL? Explain in 2 sentences.")
print(result)
