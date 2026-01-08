"""
RAG Basic Example

Demonstrates basic RAG (Retrieval Augmented Generation) with an Agent.

Requirements:
    pip install praisonaiagents
    
Environment:
    OPENAI_API_KEY - Required for LLM calls
"""

import os
from praisonaiagents import Agent

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

# Create a sample document
sample_doc = "/tmp/rag_basic_doc.txt"
with open(sample_doc, "w") as f:
    f.write("""
Machine Learning Fundamentals

Machine learning is a subset of artificial intelligence that enables systems
to learn and improve from experience without being explicitly programmed.

Types of Machine Learning:
1. Supervised Learning - Learning from labeled data
2. Unsupervised Learning - Finding patterns in unlabeled data
3. Reinforcement Learning - Learning through trial and error

Common Algorithms:
- Linear Regression
- Decision Trees
- Neural Networks
- Support Vector Machines
""")

# Create agent with RAG
agent = Agent(
    name="MLExpert",
    instructions="You are a machine learning expert. Answer questions based on the provided context.",
    knowledge=[sample_doc],
    user_id="rag_user",
    llm="openai/gpt-4o-mini",
    output="minimal",
)

print("=" * 60)
print("RAG Basic Example")
print("=" * 60)

# Query with RAG
print("\nQuery: What are the types of machine learning?")
response = agent.chat("What are the types of machine learning?")
print(f"Response: {response}")

print("\nQuery: What algorithms are commonly used?")
response = agent.chat("What algorithms are commonly used?")
print(f"Response: {response}")

# Cleanup
os.remove(sample_doc)

print("\n" + "=" * 60)
print("Example completed successfully!")
print("=" * 60)
