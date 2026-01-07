"""
AutoRagAgent Basic Example

Demonstrates basic usage of AutoRagAgent for automatic RAG retrieval decision.
AutoRagAgent wraps an Agent and decides when to retrieve context based on query heuristics.

Requirements:
    pip install praisonaiagents
    
Environment:
    OPENAI_API_KEY - Required for LLM calls
"""

import os
from praisonaiagents import Agent, AutoRagAgent

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

# Create a sample document for testing
sample_doc = "/tmp/sample_doc.txt"
with open(sample_doc, "w") as f:
    f.write("""
PraisonAI Framework Documentation

PraisonAI is an AI agents framework that supports:
- Single agent workflows
- Multi-agent collaboration
- RAG (Retrieval Augmented Generation)
- Tool integration
- Memory and context management

Key Features:
1. AutoRagAgent - Automatic retrieval decision
2. Knowledge bases - Document indexing and search
3. Hybrid retrieval - Dense + BM25 search
4. Reranking - Improve result relevance
""")

# Create agent with knowledge
agent = Agent(
    name="DocBot",
    instructions="You are a helpful documentation assistant. Answer questions based on the provided context.",
    knowledge=[sample_doc],
    user_id="example_user",  # Required for RAG retrieval
    llm="openai/gpt-4o-mini",
    verbose=False,
)

# Wrap with AutoRagAgent (default: auto policy)
auto_rag = AutoRagAgent(agent=agent)

print("=" * 60)
print("AutoRagAgent Basic Example")
print("=" * 60)

# Test 1: Question that should trigger retrieval
print("\n[Test 1] Question about documentation (should retrieve):")
response = auto_rag.chat("What features does PraisonAI support?")
print(f"Response: {response}")

# Test 2: Short greeting that should skip retrieval
print("\n[Test 2] Short greeting (should skip retrieval):")
response = auto_rag.chat("Hi!")
print(f"Response: {response}")

# Test 3: Another question
print("\n[Test 3] Another question (should retrieve):")
response = auto_rag.chat("What is AutoRagAgent?")
print(f"Response: {response}")

# Cleanup
os.remove(sample_doc)

print("\n" + "=" * 60)
print("Example completed successfully!")
print("=" * 60)
