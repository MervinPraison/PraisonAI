"""
Messages Capability Example

Demonstrates Anthropic-style messages API and token counting.
"""

from praisonai.capabilities import messages_create, count_tokens

# Create a message (Anthropic-style)
print("=== Messages Create ===")
result = messages_create(
    messages=[{"role": "user", "content": "What is the meaning of life? Answer briefly."}],
    model="gpt-4o-mini",  # Works with any model via LiteLLM
    max_tokens=100,
    system="You are a philosophical assistant."
)
print(f"Message ID: {result.id}")
if result.content:
    for block in result.content:
        if block.get("type") == "text":
            print(f"Response: {block.get('text')}")
print(f"Usage: {result.usage}")

# Count tokens
print("\n=== Token Counting ===")
result = count_tokens(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you today?"}
    ],
    model="gpt-4o-mini"
)
print(f"Token count: {result.input_tokens}")
