"""
Vector Store Adapters for PraisonAI.

Provides concrete implementations of VectorStoreProtocol:
- ChromaVectorStore: Uses ChromaDB
- PineconeVectorStore: Uses Pinecone
- QdrantVectorStore: Uses Qdrant
- WeaviateVectorStore: Uses Weaviate
"""

import os
import logging
from typing import Any, Dict, List, Optional
import uuid as uuid_module

logger = logging.getLogger(__name__)

# Import centralized availability checking
from .._framework_availability import is_available


class ChromaVectorStore:
    """ChromaDB vector store adapter."""
    
    name: str = "chroma"
    _COLLECTION_METADATA = {"hnsw:space": "cosine"}
    
    def _get_collection(self, namespace: Optional[str] = None):
        """Single source of truth for namespace -> collection resolution.

        Ad-hoc namespaces are materialised with the same distance metric as the
        primary collection so cross-namespace scores stay comparable.
        """
        if not namespace or namespace == self.namespace:
            return self._collection
        collection = self._client.get_or_create_collection(
            name=namespace,
            metadata=self._COLLECTION_METADATA,
        )
        self._warn_on_metric_mismatch(collection)
        return collection

    def _warn_on_metric_mismatch(self, collection) -> None:
        """Warn once per collection if a legacy collection is not on cosine.

        ``get_or_create_collection`` never changes the distance metric of a
        collection that already exists, so a namespace created by an older
        build can persist on L2 while new ones use cosine — making
        ``score = 1 - distance`` incomparable. We surface this instead of
        silently returning drifting scores. Migration is left to the caller
        because it requires a destructive rebuild of stored vectors.
        """
        try:
            stored = (collection.metadata or {}).get("hnsw:space")
        except Exception:
            return
        expected = self._COLLECTION_METADATA["hnsw:space"]
        if stored and stored != expected and collection.name not in self._metric_warned:
            self._metric_warned.add(collection.name)
            logger.warning(
                "Chroma collection %r uses distance metric %r, expected %r. "
                "Scores from this namespace are not comparable to cosine "
                "namespaces; recreate it to migrate.",
                collection.name, stored, expected,
            )
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None,
        persist_directory: Optional[str] = None
    ):
        if not is_available("chromadb"):
            raise ImportError(
                "chromadb is required for ChromaVectorStore. "
                "Install with: pip install chromadb"
            )
        
        import chromadb
        from chromadb.config import Settings
        
        self.config = config or {}
        self.namespace = namespace or "default"
        self.persist_directory = persist_directory or self.config.get("path", ".praison/chroma")
        self._metric_warned: set = set()
        
        # REMOVED: os.environ['ANONYMIZED_TELEMETRY'] = 'False'
        # Per-instance Settings(anonymized_telemetry=False) already covers this safely.
        
        # Create client
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.namespace,
            metadata=self._COLLECTION_METADATA
        )
        self._warn_on_metric_mismatch(self._collection)
    
    def add(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None
    ) -> List[str]:
        """Add vectors to ChromaDB."""
        ids = ids or [str(uuid_module.uuid4()) for _ in texts]
        
        # ChromaDB requires non-empty metadata dicts
        # Ensure each metadata dict has at least one key
        if metadatas is None:
            metadatas = [{"_source": "praisonai"} for _ in texts]
        else:
            # Ensure no empty dicts - add placeholder if empty
            metadatas = [
                m if m else {"_source": "praisonai"} 
                for m in metadatas
            ]
        
        collection = self._get_collection(namespace)
        
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        return ids
    
    def query(
        self,
        embedding: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Query ChromaDB by similarity."""
        from praisonaiagents.knowledge.vector_store import VectorRecord
        
        collection = self._get_collection(namespace)
        
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=filter,
            include=["documents", "metadatas", "distances", "embeddings"]
        )
        
        records = []
        if results and results['ids'] and results['ids'][0]:
            embeddings = (results.get('embeddings') or [[]])[0]
            for i, id_ in enumerate(results['ids'][0]):
                records.append(VectorRecord(
                    id=id_,
                    text=results['documents'][0][i] if results.get('documents') else "",
                    embedding=embeddings[i] if i < len(embeddings) else [],  # stored, not query
                    metadata=results['metadatas'][0][i] if results.get('metadatas') else {},
                    score=1 - results['distances'][0][i] if results.get('distances') else 1.0
                ))
        
        return records
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """Delete vectors from ChromaDB."""
        collection = self._get_collection(namespace)
        
        if delete_all:
            count = collection.count()
            name = collection.name
            # Delete and recreate the SAME namespace the caller targeted,
            # preserving the distance metric.
            self._client.delete_collection(name)
            recreated = self._client.get_or_create_collection(
                name=name,
                metadata=self._COLLECTION_METADATA
            )
            # Refresh the cached handle only if we rebuilt the default one.
            if name == self.namespace:
                self._collection = recreated
            return count
        
        if ids:
            collection.delete(ids=ids)
            return len(ids)
        
        if filter:
            # Get matching IDs first
            results = collection.get(where=filter)
            if results and results['ids']:
                collection.delete(ids=results['ids'])
                return len(results['ids'])
        
        return 0
    
    def count(self, namespace: Optional[str] = None) -> int:
        """Get count of vectors."""
        return self._get_collection(namespace).count()
    
    def get(
        self,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> List[Any]:
        """Get vectors by ID."""
        from praisonaiagents.knowledge.vector_store import VectorRecord
        
        collection = self._get_collection(namespace)
        
        results = collection.get(ids=ids, include=["documents", "metadatas", "embeddings"])
        
        records = []
        if results and results['ids']:
            for i, id_ in enumerate(results['ids']):
                records.append(VectorRecord(
                    id=id_,
                    text=results['documents'][i] if results.get('documents') else "",
                    embedding=results['embeddings'][i] if results.get('embeddings') else [],
                    metadata=results['metadatas'][i] if results.get('metadatas') else {}
                ))
        
        return records


class PineconeVectorStore:
    """Pinecone vector store adapter."""
    
    name: str = "pinecone"
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None
    ):
        if not is_available("pinecone"):
            raise ImportError(
                "pinecone is required for PineconeVectorStore. "
                "Install with: pip install pinecone"
            )
        
        from pinecone import Pinecone
        
        self.config = config or {}
        self.namespace = namespace or "default"
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        self.index_name = index_name or self.config.get("index_name", "praisonai")
        
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY environment variable or api_key parameter required")
        
        self._pc = Pinecone(api_key=self.api_key)
        self._index = self._pc.Index(self.index_name)
    
    def add(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None
    ) -> List[str]:
        """Add vectors to Pinecone."""
        ids = ids or [str(uuid_module.uuid4()) for _ in texts]
        metadatas = metadatas or [{} for _ in texts]
        ns = namespace or self.namespace
        
        # Add text to metadata for retrieval
        vectors = []
        for i, (id_, embedding, metadata) in enumerate(zip(ids, embeddings, metadatas)):
            meta = metadata.copy()
            meta["text"] = texts[i]
            vectors.append({
                "id": id_,
                "values": embedding,
                "metadata": meta
            })
        
        self._index.upsert(vectors=vectors, namespace=ns)
        return ids
    
    def query(
        self,
        embedding: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Query Pinecone by similarity."""
        from praisonaiagents.knowledge.vector_store import VectorRecord
        
        ns = namespace or self.namespace
        
        results = self._index.query(
            vector=embedding,
            top_k=top_k,
            namespace=ns,
            filter=filter,
            include_metadata=True
        )
        
        records = []
        for match in results.get("matches", []):
            metadata = match.get("metadata", {})
            text = metadata.pop("text", "")
            records.append(VectorRecord(
                id=match["id"],
                text=text,
                embedding=embedding,
                metadata=metadata,
                score=match.get("score", 0.0)
            ))
        
        return records
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """Delete vectors from Pinecone."""
        ns = namespace or self.namespace
        
        if delete_all:
            self._index.delete(delete_all=True, namespace=ns)
            return -1  # Pinecone doesn't return count
        
        if ids:
            self._index.delete(ids=ids, namespace=ns)
            return len(ids)
        
        if filter:
            self._index.delete(filter=filter, namespace=ns)
            return -1
        
        return 0
    
    def count(self, namespace: Optional[str] = None) -> int:
        """Get count of vectors."""
        ns = namespace or self.namespace
        stats = self._index.describe_index_stats()
        ns_stats = stats.get("namespaces", {}).get(ns, {})
        return ns_stats.get("vector_count", 0)
    
    def get(
        self,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> List[Any]:
        """Get vectors by ID."""
        from praisonaiagents.knowledge.vector_store import VectorRecord
        
        ns = namespace or self.namespace
        results = self._index.fetch(ids=ids, namespace=ns)
        
        records = []
        for id_, data in results.get("vectors", {}).items():
            metadata = data.get("metadata", {})
            text = metadata.pop("text", "")
            records.append(VectorRecord(
                id=id_,
                text=text,
                embedding=data.get("values", []),
                metadata=metadata
            ))
        
        return records


def register_default_vector_stores():
    """Register all default vector stores with the registry."""
    from praisonaiagents.knowledge.vector_store import get_vector_store_registry
    
    registry = get_vector_store_registry()
    
    # Register ChromaDB
    if is_available("chromadb"):
        registry.register("chroma", ChromaVectorStore)
    
    # Register Pinecone
    if is_available("pinecone"):
        registry.register("pinecone", PineconeVectorStore)
    
    logger.debug("Registered default vector stores")


# NOTE: No auto-registration at import time. Mutating the core-SDK vector-store
# registry and probing for chromadb / pinecone on disk as an import side effect
# violates the "core stays lightweight, wrapper does the heavy work at call
# time" principle and makes this module unsafe to import in tests / multi-tenant
# runtimes. Callers that want these backends wired into the SDK registry must
# invoke ``register_default_vector_stores()`` explicitly, e.g.::
#
#     from praisonai.adapters.vector_stores import register_default_vector_stores
#     register_default_vector_stores()
