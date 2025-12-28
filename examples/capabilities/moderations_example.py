"""
Moderations Capability Example

Demonstrates content moderation using PraisonAI capabilities.
"""

from praisonai.capabilities import moderate

# Check safe content
print("=== Safe Content Check ===")
result = moderate(
    input="Hello, how are you today?"
)
print(f"Flagged: {result[0].flagged}")
print(f"Categories: {list(result[0].categories.keys())[:5]}...")

# Check multiple texts
print("\n=== Multiple Text Moderation ===")
result = moderate(
    input=["Hello world", "Have a nice day", "This is a test"]
)
print(f"Number of results: {len(result)}")
for i, r in enumerate(result):
    print(f"  Text {i+1}: Flagged = {r.flagged}")
