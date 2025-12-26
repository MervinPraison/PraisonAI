"""PGVector Knowledge Store - Agent-First Example (requires Docker)

Docker: docker run -d --name pgvector -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg16
"""
import os
from praisonaiagents import Agent

url = os.getenv("PGVECTOR_URL", "postgresql://postgres:postgres@localhost:5433/postgres")

# Agent-first approach: use knowledge parameter with PGVector
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge_config={
        "vector_store": "pgvector",
        "url": url
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: PGVector with Agent")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence import create_knowledge_store
# store = create_knowledge_store("pgvector", url=url)
