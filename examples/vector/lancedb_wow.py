"""LanceDB Vector Store - Basic Test"""
import sys
sys.path.insert(0, 'src/praisonai')
try:
    from praisonai.persistence import create_knowledge_store
    from praisonai.persistence.knowledge.base import KnowledgeDocument
    
    store = create_knowledge_store("lancedb", path="/tmp/lancedb_demo")
    store.create_collection("demo", dimension=1536)
    docs = [
        KnowledgeDocument(id="doc1", content="The Eiffel Tower is in Paris", embedding=[0.1]*1536),
        KnowledgeDocument(id="doc2", content="The Statue of Liberty is in New York", embedding=[0.2]*1536)
    ]
    store.insert("demo", docs)
    results = store.search("demo", query_embedding=[0.1]*1536, limit=1)
    print(f"Found: {len(results)} results")
    assert len(results) >= 1
    print("PASSED: LanceDB vector store")
except ImportError as e:
    print(f"SKIPPED: LanceDB - {e}")
