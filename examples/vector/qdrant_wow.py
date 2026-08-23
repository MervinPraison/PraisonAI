"""Qdrant Vector Store - Agent-First Example

Qdrant is not a shipped adapter. Register one first, then use it via the
``knowledge`` parameter. If no adapter is registered this example skips
cleanly instead of crashing.

    from praisonaiagents.knowledge.adapters import register_knowledge_adapter
    register_knowledge_adapter("qdrant", MyQdrantAdapter)
"""
import sys
from praisonaiagents import Agent
from praisonaiagents.knowledge.adapters import list_knowledge_adapters

if "qdrant" not in list_knowledge_adapters():
    print("SKIPPED: Qdrant - no 'qdrant' adapter registered")
    sys.exit(0)

# Agent-first approach: use knowledge parameter with a registered Qdrant adapter
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge={"sources": ["./docs/guide.pdf"], "vector_store": {"provider": "qdrant"}}
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: Qdrant with Agent")
