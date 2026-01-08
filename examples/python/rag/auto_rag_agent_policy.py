"""
AutoRagAgent Policy Example

Demonstrates different retrieval policies:
- auto: Decides based on query heuristics (default)
- always: Always retrieves context
- never: Never retrieves, direct chat only

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

# Create a sample document
sample_doc = "/tmp/policy_doc.txt"
with open(sample_doc, "w") as f:
    f.write("""
Company Return Policy

Our return policy allows returns within 30 days of purchase.
Items must be in original condition with tags attached.
Refunds are processed within 5-7 business days.
Exchanges are available for different sizes or colors.
""")

# Create base agent with knowledge
agent = Agent(
    name="PolicyBot",
    instructions="You are a customer service assistant.",
    knowledge=[sample_doc],
    user_id="policy_user",
    llm="openai/gpt-4o-mini",
    output="minimal",
)

print("=" * 60)
print("AutoRagAgent Policy Example")
print("=" * 60)

# Policy 1: AUTO (default)
print("\n[Policy: AUTO] - Decides based on query heuristics")
auto_rag = AutoRagAgent(agent=agent, retrieval_policy="auto")

print("  Query: 'What is the return policy?' (should retrieve)")
response = auto_rag.chat("What is the return policy?")
print(f"  Response: {response[:200]}...")

print("\n  Query: 'Hello' (should skip)")
response = auto_rag.chat("Hello")
print(f"  Response: {response}")

# Policy 2: ALWAYS
print("\n" + "-" * 60)
print("[Policy: ALWAYS] - Always retrieves context")
always_rag = AutoRagAgent(agent=agent, retrieval_policy="always")

print("  Query: 'Hello' (will retrieve even for greeting)")
response = always_rag.chat("Hello")
print(f"  Response: {response[:200]}...")

# Policy 3: NEVER
print("\n" + "-" * 60)
print("[Policy: NEVER] - Never retrieves, direct chat only")
never_rag = AutoRagAgent(agent=agent, retrieval_policy="never")

print("  Query: 'What is the return policy?' (will NOT retrieve)")
response = never_rag.chat("What is the return policy?")
print(f"  Response: {response[:200]}...")

# Per-call overrides
print("\n" + "-" * 60)
print("[Per-call Overrides]")

print("  Force retrieval on 'auto' policy:")
response = auto_rag.chat("Hi there", force_retrieval=True)
print(f"  Response: {response[:200]}...")

print("\n  Skip retrieval on 'auto' policy:")
response = auto_rag.chat("What is the return window?", skip_retrieval=True)
print(f"  Response: {response[:200]}...")

# Cleanup
os.remove(sample_doc)

print("\n" + "=" * 60)
print("Example completed successfully!")
print("=" * 60)
