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

# Lazy import flags
_CHROMA_AVAILABLE = None
_PINECONE_AVAILABLE = None
_QDRANT_AVAILABLE = None
_WEAVIATE_AVAILABLE = None


def _check_chroma():
    """Check if chromadb is available."""
    global _CHROMA_AVAILABLE
    if _CHROMA_AVAILABLE is None:
        import importlib.util
        _CHROMA_AVAILABLE = importlib.util.find_spec("chromadb") is not None
    return _CHROMA_AVAILABLE


def _check_pinecone():
    """Check if pinecone is available."""
    global _PINECONE_AVAILABLE
    if _PINECONE_AVAILABLE is None:
        import importlib.util
        _PINECONE_AVAILABLE = importlib.util.find_spec("pinecone") is not None
    return _PINECONE_AVAILABLE


def _check_qdrant():
    """Check if qdrant_client is available."""
    global _QDRANT_AVAILABLE
    if _QDRANT_AVAILABLE is None:
        import importlib.util
        _QDRANT_AVAILABLE = importlib.util.find_spec("qdrant_client") is not None
    return _QDRANT_AVAILABLE


def _check_weaviate():
    """Check if weaviate is available."""
    global _WEAVIATE_AVAILABLE
    if _WEAVIATE_AVAILABLE is None:
        import importlib.util
        _WEAVIATE_AVAILABLE = importlib.util.find_spec("weaviate") is not None
    return _WEAVIATE_AVAILABLE


class ChromaVectorStore:
    """ChromaDB vector store adapter."""
    
    name: str = "chroma"
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None,
        persist_directory: Optional[str] = None
    ):
        if not _check_chroma():
            raise ImportError(
                "chromadb is required for ChromaVectorStore. "
                "Install with: pip install chromadb"
            )
        
        import chromadb
        from chromadb.config import Settings
        
        self.config = config or {}
        self.namespace = namespace or "default"
        self.persist_directory = persist_directory or self.config.get("path", ".praison/chroma")
        
        # Disable telemetry
        os.environ['ANONYMIZED_TELEMETRY'] = 'False'
        
        # Create client
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.namespace,
            metadata={"hnsw:space": "cosine"}
        )
    
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
        
        # Use different collection if namespace specified
        if namespace and namespace != self.namespace:
            collection = self._client.get_or_create_collection(name=namespace)
        else:
            collection = self._collection
        
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
        
        if namespace and namespace != self.namespace:
            collection = self._client.get_or_create_collection(name=namespace)
        else:
            collection = self._collection
        
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=filter
        )
        
        records = []
        if results and results['ids'] and results['ids'][0]:
            for i, id_ in enumerate(results['ids'][0]):
                records.append(VectorRecord(
                    id=id_,
                    text=results['documents'][0][i] if results.get('documents') else "",
                    embedding=embedding,  # We don't get embeddings back from query
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
        if namespace and namespace != self.namespace:
            collection = self._client.get_or_create_collection(name=namespace)
        else:
            collection = self._collection
        
        if delete_all:
            count = collection.count()
            # Delete collection and recreate
            self._client.delete_collection(collection.name)
            self._collection = self._client.get_or_create_collection(
                name=self.namespace,
                metadata={"hnsw:space": "cosine"}
            )
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
        if namespace and namespace != self.namespace:
            collection = self._client.get_or_create_collection(name=namespace)
        else:
            collection = self._collection
        return collection.count()
    
    def get(
        self,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> List[Any]:
        """Get vectors by ID."""
        from praisonaiagents.knowledge.vector_store import VectorRecord
        
        if namespace and namespace != self.namespace:
            collection = self._client.get_or_create_collection(name=namespace)
        else:
            collection = self._collection
        
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
        if not _check_pinecone():
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
    if _check_chroma():
        registry.register("chroma", ChromaVectorStore)
    
    # Register Pinecone
    if _check_pinecone():
        registry.register("pinecone", PineconeVectorStore)
    
    logger.debug("Registered default vector stores")


# Auto-register on import
register_default_vector_stores()
