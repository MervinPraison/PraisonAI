"""
Embeddings Capability Example

Demonstrates text embedding generation using PraisonAI capabilities.
"""

from praisonai.capabilities import embed

# Single text embedding
print("=== Single Text Embedding ===")
result = embed(
    input="Hello, world!",
    model="text-embedding-3-small"
)
print(f"Embedding dimensions: {len(result.embeddings[0])}")
print(f"First 5 values: {result.embeddings[0][:5]}")
print(f"Usage: {result.usage}")

# Multiple text embeddings
print("\n=== Multiple Text Embeddings ===")
result = embed(
    input=["Hello", "World", "AI"],
    model="text-embedding-3-small"
)
print(f"Number of embeddings: {len(result.embeddings)}")
for i, emb in enumerate(result.embeddings):
    print(f"  Text {i+1}: {len(emb)} dimensions")
