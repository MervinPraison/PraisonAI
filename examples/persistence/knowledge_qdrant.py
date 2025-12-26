"""
Qdrant Knowledge Store - Agent-First Example

Demonstrates using Qdrant for knowledge-based RAG with an Agent.

Requirements:
    pip install "praisonai[tools]"

Docker Setup:
    docker run -d --name praison-qdrant -p 6333:6333 qdrant/qdrant

Run:
    python knowledge_qdrant.py

Expected Output:
    Agent responds using knowledge from documents
"""

from praisonaiagents import Agent
import tempfile
import os
import shutil

# Create sample knowledge document
sample_doc = """
# AI and Programming Guide

## Python Programming
Python is a versatile programming language used for web development, data science, and AI.
It has a simple syntax and extensive libraries.

## Machine Learning
Machine learning enables computers to learn patterns from data without explicit programming.
Common frameworks include TensorFlow, PyTorch, and scikit-learn.

## Databases
PostgreSQL is a powerful open-source relational database system.
It supports both SQL and JSON data types.
"""

# Save to temp file
temp_dir = tempfile.mkdtemp()
doc_path = os.path.join(temp_dir, "guide.txt")
with open(doc_path, "w") as f:
    f.write(sample_doc)

print("=== Qdrant Knowledge Store Demo (Agent-First) ===")

# Agent-first approach: use knowledge parameter with Qdrant
agent = Agent(
    name="KnowledgeAssistant",
    instructions="You are a helpful assistant with access to technical documentation.",
    knowledge=[doc_path],
    knowledge_config={
        "vector_store": "qdrant",
        "url": "http://localhost:6333"
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What programming language is good for AI?")
print(f"Response: {response}")

# Cleanup
shutil.rmtree(temp_dir)

print("\n=== Demo Complete ===")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence.factory import create_knowledge_store
# store = create_knowledge_store("qdrant", url="http://localhost:6333")
