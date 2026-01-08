"""
Agent vs AutoRagAgent Comparison

Demonstrates the difference between using Agent directly vs AutoRagAgent wrapper.

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
sample_doc = "/tmp/comparison_doc.txt"
with open(sample_doc, "w") as f:
    f.write("""
Product Manual: Smart Thermostat

Installation:
1. Turn off power at the circuit breaker
2. Remove old thermostat
3. Connect wires to matching terminals
4. Mount the base plate
5. Attach the display unit
6. Restore power

Features:
- Wi-Fi connectivity
- Voice control support
- Energy usage reports
- Geofencing auto-away
- Learning schedule

Troubleshooting:
- If display is blank, check power connection
- If Wi-Fi won't connect, restart router
- If temperature is inaccurate, recalibrate sensor
""")

# Create base agent with knowledge
agent = Agent(
    name="TechSupport",
    instructions="You are a technical support assistant.",
    knowledge=[sample_doc],
    user_id="comparison_user",
    llm="openai/gpt-4o-mini",
    output="minimal",
)

print("=" * 60)
print("Agent vs AutoRagAgent Comparison")
print("=" * 60)

# Using Agent directly - always uses RAG when knowledge is configured
print("\n[Using Agent Directly]")
print("Agent with knowledge always retrieves context for every query.")
print("\nQuery: 'Hello!'")
response = agent.chat("Hello!")
print(f"Response: {response}")

print("\nQuery: 'How do I install the thermostat?'")
response = agent.chat("How do I install the thermostat?")
print(f"Response: {response[:300]}...")

# Using AutoRagAgent - decides when to retrieve
print("\n" + "=" * 60)
print("[Using AutoRagAgent]")
print("AutoRagAgent decides when to retrieve based on query heuristics.")

auto_rag = AutoRagAgent(agent=agent, retrieval_policy="auto")

print("\nQuery: 'Hello!' (short greeting - skips retrieval)")
response = auto_rag.chat("Hello!")
print(f"Response: {response}")

print("\nQuery: 'How do I install the thermostat?' (question - retrieves)")
response = auto_rag.chat("How do I install the thermostat?")
print(f"Response: {response[:300]}...")

# Summary
print("\n" + "=" * 60)
print("Summary:")
print("-" * 60)
print("""
| Approach      | Retrieval Behavior              | Best For                    |
|---------------|--------------------------------|------------------------------|
| Agent         | Always retrieves (if knowledge)| Consistent RAG responses     |
| AutoRagAgent  | Decides per query              | Mixed chat + RAG workloads   |

AutoRagAgent is ideal when:
- You have a chatbot that sometimes needs knowledge, sometimes doesn't
- You want to reduce unnecessary retrieval overhead
- You need fine-grained control over retrieval behavior
""")

# Cleanup
os.remove(sample_doc)

print("=" * 60)
print("Example completed successfully!")
print("=" * 60)
