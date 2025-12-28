"""
Completions Capability Example

Demonstrates chat and text completions using PraisonAI capabilities.
"""

from praisonai.capabilities import chat_completion, text_completion

# Chat completion example
print("=== Chat Completion ===")
result = chat_completion(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2 + 2? Answer in one word."}
    ],
    model="gpt-4o-mini",
    max_tokens=10
)
print(f"Response: {result.content}")
print(f"Model: {result.model}")
print(f"Usage: {result.usage}")

# Text completion example (legacy)
print("\n=== Text Completion ===")
result = text_completion(
    prompt="The capital of France is",
    model="gpt-3.5-turbo-instruct",
    max_tokens=10
)
print(f"Response: {result.content}")
