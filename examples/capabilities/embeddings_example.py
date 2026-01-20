"""
Embeddings Capability Example

Demonstrates text embedding generation using PraisonAI capabilities.
Both `embed` and `embedding` work identically - use whichever you prefer.
"""

from praisonai import embed, embedding  # Both work from top-level
# Or: from praisonai.capabilities import embed, embedding

# Single text embedding using embed()
print("=== Single Text Embedding (using embed) ===")
result = embed(
    input="Hello, world!",
    model="text-embedding-3-small"
)
print(f"Embedding dimensions: {len(result.embeddings[0])}")
print(f"First 5 values: {result.embeddings[0][:5]}")
print(f"Usage: {result.usage}")

# Same thing using embedding() alias
print("\n=== Single Text Embedding (using embedding alias) ===")
result = embedding(
    input="Hello, world!",
    model="text-embedding-3-small"
)
print(f"Embedding dimensions: {len(result.embeddings[0])}")

# Multiple text embeddings
print("\n=== Multiple Text Embeddings ===")
result = embed(
    input=["Hello", "World", "AI"],
    model="text-embedding-3-small"
)
print(f"Number of embeddings: {len(result.embeddings)}")
for i, emb in enumerate(result.embeddings):
    print(f"  Text {i+1}: {len(emb)} dimensions")

# With custom dimensions (for models that support it)
print("\n=== Custom Dimensions ===")
result = embed(
    input="Hello world",
    model="text-embedding-3-large",
    dimensions=256
)
print(f"Reduced dimensions: {len(result.embeddings[0])}")
