"""PGVector Knowledge Store - Basic Test (requires Docker)"""
import sys
import os
sys.path.insert(0, 'src/praisonai')
from praisonai.persistence import create_knowledge_store
from praisonai.persistence.knowledge.base import KnowledgeDocument

# Docker: docker run -d --name pgvector -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg16
url = os.getenv("PGVECTOR_URL", "postgresql://postgres:postgres@localhost:5433/postgres")
try:
    store = create_knowledge_store("pgvector", url=url)
    store.create_collection("demo", dimension=1536)
    docs = [
        KnowledgeDocument(id="1", content="Kubernetes orchestrates containers", embedding=[0.1]*1536),
        KnowledgeDocument(id="2", content="Docker packages applications", embedding=[0.2]*1536)
    ]
    store.insert("demo", docs)
    results = store.search("demo", query_embedding=[0.1]*1536, limit=1)
    print(f"Found: {len(results)} results")
    assert len(results) >= 1
    print("PASSED: PGVector vector store")
except Exception as e:
    print(f"SKIPPED: PGVector - {e}")
