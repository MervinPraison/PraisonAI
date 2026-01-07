"""
Basic Agent Retrieval Example

Demonstrates the Agent-first retrieval API with knowledge and retrieval_config.
"""

import os
from praisonaiagents import Agent

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

# Create a simple text file for testing
test_content = """
# PraisonAI Framework Overview

PraisonAI is an AI agents framework that enables building sophisticated AI applications.

## Key Features

1. **Agent-First Design**: Everything centers around the Agent class
2. **Knowledge Integration**: Agents can use knowledge bases for retrieval
3. **Unified Configuration**: Single retrieval_config for all retrieval settings
4. **Multi-Agent Support**: Multiple agents can share knowledge

## Retrieval Policies

- **auto**: Automatically decide when to retrieve based on query
- **always**: Always retrieve for every query
- **never**: Never retrieve (use for pure generation)

## Citation Modes

- **append**: Add citations at the end of the response
- **inline**: Include citations inline in the text
- **hidden**: Citations available in result but not in text
"""

# Write test content to a file
os.makedirs(".praison/test_docs", exist_ok=True)
with open(".praison/test_docs/overview.txt", "w") as f:
    f.write(test_content)

print("=" * 60)
print("Basic Agent Retrieval Example")
print("=" * 60)

# Create agent with knowledge and retrieval config
agent = Agent(
    name="Knowledge Agent",
    instructions="You are a helpful assistant that answers questions based on the provided knowledge. Be concise.",
    knowledge=[".praison/test_docs/overview.txt"],
    retrieval_config={
        "policy": "always",      # Always retrieve for this demo
        "top_k": 3,              # Get top 3 chunks
        "citations": True,       # Include citations
        "max_context_tokens": 2000,
    }
)

# Test 1: Basic chat with retrieval
print("\n1. Basic Chat with Retrieval:")
print("-" * 40)
response = agent.chat("What are the key features of PraisonAI?")
print(response)

# Test 2: Query with structured result
print("\n2. Structured Query with Citations:")
print("-" * 40)
try:
    result = agent.query("What are the retrieval policies?")
    print(f"Answer: {result.answer}")
    if result.citations:
        print(f"\nCitations ({len(result.citations)}):")
        for citation in result.citations:
            print(f"  - {citation.source}")
except Exception as e:
    print(f"Query not available (RAG module may not be installed): {e}")

# Test 3: Retrieve only (no LLM generation)
print("\n3. Retrieve Only (No LLM):")
print("-" * 40)
try:
    context = agent.retrieve("citation modes")
    print(f"Found context: {len(context.context)} chars")
    if context.citations:
        print(f"Sources: {len(context.citations)}")
except Exception as e:
    print(f"Retrieve not available (RAG module may not be installed): {e}")

# Test 4: Skip retrieval
print("\n4. Chat with skip_retrieval=True:")
print("-" * 40)
response = agent.chat("What is 2 + 2?", skip_retrieval=True)
print(response)

print("\n" + "=" * 60)
print("Example Complete!")
print("=" * 60)

# Cleanup
import shutil
shutil.rmtree(".praison/test_docs", ignore_errors=True)
