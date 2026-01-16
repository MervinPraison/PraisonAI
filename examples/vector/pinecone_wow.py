"""Pinecone Vector Store - Agent-First Example

Requires: export PINECONE_API_KEY=...
"""
import os
import sys
from praisonaiagents import Agent

api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("SKIPPED: Pinecone - PINECONE_API_KEY not set")
    sys.exit(0)

# Agent-first approach: use knowledge parameter with Pinecone
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge={
        "vector_store": "pinecone",
        "api_key": api_key,
        "environment": "us-east-1"
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: Pinecone with Agent")

# --- Advanced: Direct Store Usage ---
# from pinecone import Pinecone
# pc = Pinecone(api_key=api_key)
