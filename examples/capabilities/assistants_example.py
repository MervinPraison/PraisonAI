"""
Assistants Capabilities Example

Demonstrates OpenAI Assistants API using PraisonAI capabilities.
"""

from praisonai.capabilities import assistant_list

print("=== List Assistants ===")
try:
    assistants = assistant_list()
    print(f"Assistants found: {len(assistants)}")
    for a in assistants[:5]:  # Show first 5
        print(f"  - {a.get('name', 'unnamed')}: {a.get('id', 'unknown')}")
except Exception as e:
    print(f"Note: {e}")

print("\n=== Assistant Operations ===")
print("Available functions:")
print("  assistant_create(name, instructions, model='gpt-4o-mini')")
print("  assistant_list()")

print("\nSee CLI: praisonai assistants list")
print("See CLI: praisonai assistants create --name 'My Assistant'")
