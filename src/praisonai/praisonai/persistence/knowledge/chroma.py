"""
ChromaDB implementation of KnowledgeStore.

Requires: chromadb
Install: pip install chromadb
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class ChromaKnowledgeStore(KnowledgeStore):
    """
    ChromaDB-based knowledge store for vector search.
    
    Zero-config embedded vector database.
    
    Example:
        store = ChromaKnowledgeStore(
            path="./chroma_db"
        )
    """
    
    def __init__(
        self,
        path: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 8000,
        persistent: bool = True,
    ):
        """
        Initialize ChromaDB knowledge store.
        
        Args:
            path: Path for persistent storage (embedded mode)
            host: Chroma server host (client mode)
            port: Chroma server port
            persistent: Use persistent storage
        """
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "chromadb is required for ChromaDB support. "
                "Install with: pip install chromadb"
            )
        
        self._chromadb = chromadb
        
        if host:
            # Client mode
            self._client = chromadb.HttpClient(host=host, port=port)
        elif path and persistent:
            # Persistent embedded mode
            self._client = chromadb.PersistentClient(
                path=path,
                settings=Settings(anonymized_telemetry=False)
            )
        else:
            # In-memory mode
            self._client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False)
            )
        
        self._collections: Dict[str, Any] = {}
        logger.info(f"ChromaDB initialized (path={path}, host={host})")
    
    def _get_collection(self, name: str):
        """Get or cache a collection."""
        if name not in self._collections:
            self._collections[name] = self._client.get_collection(name)
        return self._collections[name]
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection."""
        distance_map = {
            "cosine": "cosine",
            "euclidean": "l2",
            "dot": "ip",
        }
        
        self._client.create_collection(
            name=name,
            metadata={"hnsw:space": distance_map.get(distance, "cosine"), **(metadata or {})}
        )
        logger.info(f"Created ChromaDB collection: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        try:
            self._client.delete_collection(name)
            if name in self._collections:
                del self._collections[name]
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        try:
            self._client.get_collection(name)
            return True
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        return [c.name for c in self._client.list_collections()]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents into a collection."""
        col = self._get_collection(collection)
        
        ids = []
        embeddings = []
        contents = []
        metadatas = []
        
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            ids.append(doc.id)
            embeddings.append(doc.embedding)
            contents.append(doc.content)
            metadatas.append({
                "content_hash": doc.content_hash or "",
                "created_at": doc.created_at,
                **(doc.metadata or {})
            })
        
        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        col = self._get_collection(collection)
        
        ids = []
        embeddings = []
        contents = []
        metadatas = []
        
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            ids.append(doc.id)
            embeddings.append(doc.embedding)
            contents.append(doc.content)
            metadatas.append({
                "content_hash": doc.content_hash or "",
                "created_at": doc.created_at,
                **(doc.metadata or {})
            })
        
        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )
        
        return ids
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents."""
        col = self._get_collection(collection)
        
        where = None
        if filters:
            where = {k: v for k, v in filters.items()}
        
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        
        documents = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results.get("distances") else None
                
                # Convert distance to similarity score (for cosine: 1 - distance)
                if score_threshold is not None and distance is not None:
                    score = 1 - distance
                    if score < score_threshold:
                        continue
                
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                content_hash = metadata.pop("content_hash", None)
                created_at = metadata.pop("created_at", 0)
                
                doc = KnowledgeDocument(
                    id=doc_id,
                    content=results["documents"][0][i] if results.get("documents") else "",
                    embedding=None,
                    metadata=metadata,
                    content_hash=content_hash,
                    created_at=created_at,
                )
                documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        col = self._get_collection(collection)
        
        results = col.get(
            ids=ids,
            include=["documents", "metadatas", "embeddings"],
        )
        
        documents = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                content_hash = metadata.pop("content_hash", None)
                created_at = metadata.pop("created_at", 0)
                
                doc = KnowledgeDocument(
                    id=doc_id,
                    content=results["documents"][i] if results.get("documents") else "",
                    embedding=results["embeddings"][i] if results.get("embeddings") else None,
                    metadata=metadata,
                    content_hash=content_hash,
                    created_at=created_at,
                )
                documents.append(doc)
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        col = self._get_collection(collection)
        
        if ids:
            col.delete(ids=ids)
            return len(ids)
        elif filters:
            col.delete(where=filters)
            return -1  # Unknown count
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        col = self._get_collection(collection)
        return col.count()
    
    def close(self) -> None:
        """Close the store."""
        self._collections.clear()
