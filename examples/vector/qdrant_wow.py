"""Chroma Vector Store - Agent-First Example

Uses Chroma, a shipped vector store, so this runs without extra services.

To use a provider that is not shipped (e.g. Qdrant), register an adapter
first with ``register_knowledge_adapter("qdrant", MyQdrantAdapter)`` and then
pass ``"provider": "qdrant"``.
"""
from praisonaiagents import Agent

# Agent-first approach: use knowledge parameter with a shipped vector store
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge={"sources": ["./docs/guide.pdf"], "vector_store": {"provider": "chroma"}}
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: Chroma with Agent")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence import create_knowledge_store
# store = create_knowledge_store("chroma")
