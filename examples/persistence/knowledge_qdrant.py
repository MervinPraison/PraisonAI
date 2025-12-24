"""
Qdrant Knowledge Store Example for PraisonAI.

Demonstrates vector insert + search through the knowledge store.

Requirements:
    pip install "praisonai[tools]"

Docker Setup:
    docker run -d --name praison-qdrant -p 6333:6333 qdrant/qdrant

Run:
    python knowledge_qdrant.py

Expected Output:
    === Qdrant Knowledge Store Demo ===
    Created collection: demo_knowledge
    Inserted 3 documents
    Search results: 2 documents found
"""

from praisonai.persistence.factory import create_knowledge_store
from praisonai.persistence.knowledge.base import KnowledgeDocument
import random

# Create Qdrant knowledge store
store = create_knowledge_store("qdrant", url="http://localhost:6333")

collection_name = "demo_knowledge"
dimension = 384  # Embedding dimension

# Create collection
print("=== Qdrant Knowledge Store Demo ===")
if store.collection_exists(collection_name):
    store.delete_collection(collection_name)

store.create_collection(collection_name, dimension=dimension)
print(f"Created collection: {collection_name}")

# Create sample documents with embeddings
random.seed(42)
documents = [
    KnowledgeDocument(
        id="doc-1",
        content="Python is a versatile programming language used for web development, data science, and AI.",
        embedding=[random.random() for _ in range(dimension)],
        metadata={"category": "programming", "language": "python"}
    ),
    KnowledgeDocument(
        id="doc-2", 
        content="Machine learning enables computers to learn patterns from data without explicit programming.",
        embedding=[random.random() for _ in range(dimension)],
        metadata={"category": "ai", "topic": "ml"}
    ),
    KnowledgeDocument(
        id="doc-3",
        content="PostgreSQL is a powerful open-source relational database system.",
        embedding=[random.random() for _ in range(dimension)],
        metadata={"category": "database", "type": "sql"}
    ),
]

# Insert documents
ids = store.insert(collection_name, documents)
print(f"Inserted {len(ids)} documents")

# Search for similar documents
query_embedding = [random.random() for _ in range(dimension)]
results = store.search(collection_name, query_embedding, limit=2)
print(f"Search results: {len(results)} documents found")

for doc in results:
    print(f"  - {doc.id}: {doc.content[:50]}...")

# Cleanup
store.delete_collection(collection_name)
store.close()

print("\n=== Demo Complete ===")
