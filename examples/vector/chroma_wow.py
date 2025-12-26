"""ChromaDB Vector Store - Basic Test"""
import sys
sys.path.insert(0, 'src/praisonai')
from praisonai.persistence import create_knowledge_store
from praisonai.persistence.knowledge.base import KnowledgeDocument

store = create_knowledge_store("chroma", path="/tmp/chroma_demo")
try:
    store.delete_collection("demo")
except Exception:
    pass
store.create_collection("demo", dimension=1536)
docs = [
    KnowledgeDocument(id="1", content="Python is a programming language", embedding=[0.1]*1536),
    KnowledgeDocument(id="2", content="JavaScript runs in browsers", embedding=[0.2]*1536)
]
store.insert("demo", docs)
results = store.search("demo", query_embedding=[0.1]*1536, limit=1)
print(f"Found: {len(results)} results")
assert len(results) >= 1
print("PASSED: ChromaDB vector store")
