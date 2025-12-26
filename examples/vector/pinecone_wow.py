"""Pinecone Vector Store - Real API Test"""
import os
import sys
sys.path.insert(0, 'src/praisonai')

# Requires: export PINECONE_API_KEY=...
api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("SKIPPED: Pinecone - PINECONE_API_KEY not set")
    sys.exit(0)

from pinecone import Pinecone

pc = Pinecone(api_key=api_key)
indexes = pc.list_indexes()
print(f"Pinecone connected! Found {len(list(indexes))} indexes")

# Use existing 'test' index or create one
index_name = "test"
if index_name not in [idx.name for idx in pc.list_indexes()]:
    print(f"SKIPPED: Pinecone - index '{index_name}' not found")
    sys.exit(0)

index = pc.Index(index_name)
stats = index.describe_index_stats()
print(f"Index '{index_name}' has {stats.total_vector_count} vectors")
print("PASSED: Pinecone vector store")
