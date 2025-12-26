"""Qdrant Vector Store - Basic Test (requires Docker)"""
import sys, os
sys.path.insert(0, 'src/praisonai')
from praisonai.persistence import create_knowledge_store
from praisonai.persistence.knowledge.base import KnowledgeDocument

# Docker: docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
url = os.getenv("QDRANT_URL", "http://localhost:6333")
store = create_knowledge_store("qdrant", url=url)
try:
    store.delete_collection("demo")
except Exception:
    pass
store.create_collection("demo", dimension=1536)
docs = [
    KnowledgeDocument(id="1", content="Machine learning is AI", embedding=[0.1]*1536),
    KnowledgeDocument(id="2", content="Deep learning uses neural nets", embedding=[0.2]*1536)
]
store.insert("demo", docs)
results = store.search("demo", query_embedding=[0.1]*1536, limit=1)
print(f"Found: {len(results)} results")
assert len(results) >= 1
print("PASSED: Qdrant vector store")
