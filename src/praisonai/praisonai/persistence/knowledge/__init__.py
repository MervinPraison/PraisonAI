"""
KnowledgeStore implementations for vector embeddings and semantic search.

Supported backends:
- Qdrant (qdrant)
- Pinecone (pinecone)
- ChromaDB (chroma)
- Weaviate (weaviate)
- LanceDB (lancedb)
- Milvus (milvus)
- PGVector (pgvector)
- Redis Vector (redis)
- Cassandra Vector (cassandra)
- ClickHouse Vector (clickhouse)
"""

__all__ = [
    "KnowledgeStore",
    "KnowledgeDocument",
]

def __getattr__(name: str):
    if name in ("KnowledgeStore", "KnowledgeDocument"):
        from .base import KnowledgeStore, KnowledgeDocument
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
