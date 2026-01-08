"""
RAG with Citations Example

Demonstrates RAG with citation tracking for source attribution.

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

# Create multiple sample documents
doc1 = "/tmp/citation_doc1.txt"
with open(doc1, "w") as f:
    f.write("""
Research Paper: Climate Change Effects

Global temperatures have risen by 1.1°C since pre-industrial times.
Sea levels are rising at 3.3mm per year.
Arctic ice is declining at 13% per decade.
""")

doc2 = "/tmp/citation_doc2.txt"
with open(doc2, "w") as f:
    f.write("""
Research Paper: Renewable Energy

Solar energy capacity has grown 20x in the last decade.
Wind power now provides 7% of global electricity.
Battery storage costs have dropped 89% since 2010.
""")

# Create agent with multiple knowledge sources
agent = Agent(
    name="ResearchBot",
    instructions="You are a research assistant. Always cite your sources.",
    knowledge=[doc1, doc2],
    user_id="citation_user",
    llm="openai/gpt-4o-mini",
    output="minimal",
)

print("=" * 60)
print("RAG with Citations Example")
print("=" * 60)

# AutoRagAgent with citations enabled (default)
auto_rag = AutoRagAgent(
    agent=agent,
    citations=True,  # Include citations in response
)

print("\nQuery: What are the key climate change statistics?")
response = auto_rag.chat("What are the key climate change statistics?")
print(f"Response:\n{response}")

print("\n" + "-" * 60)
print("\nQuery: How has renewable energy grown?")
response = auto_rag.chat("How has renewable energy grown?")
print(f"Response:\n{response}")

# Without citations
print("\n" + "-" * 60)
print("\n[Without Citations]")
auto_rag_no_cite = AutoRagAgent(agent=agent, citations=False)
response = auto_rag_no_cite.chat("What is the rate of sea level rise?")
print(f"Response: {response}")

# Cleanup
os.remove(doc1)
os.remove(doc2)

print("\n" + "=" * 60)
print("Example completed successfully!")
print("=" * 60)
