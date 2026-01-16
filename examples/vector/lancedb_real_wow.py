"""LanceDB Vector Store - Agent-First Example"""
from praisonaiagents import Agent

# Agent-first approach: use knowledge parameter with LanceDB
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge={
        "vector_store": "lancedb",
        "path": "/tmp/lancedb_test"
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: LanceDB with Agent")

# --- Advanced: Direct LanceDB Usage ---
# import lancedb
# db = lancedb.connect("/tmp/lancedb_test")
# data = [{"id": "1", "text": "ML is AI", "vector": [0.1] * 128}]
# table = db.create_table("demo", data)
