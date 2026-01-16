"""Qdrant Vector Store - Agent-First Example (requires Docker)

Docker: docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
"""
import os
from praisonaiagents import Agent

# Agent-first approach: use knowledge parameter with Qdrant
url = os.getenv("QDRANT_URL", "http://localhost:6333")

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge={
        "vector_store": "qdrant",
        "url": url
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: Qdrant with Agent")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence import create_knowledge_store
# store = create_knowledge_store("qdrant", url=url)
