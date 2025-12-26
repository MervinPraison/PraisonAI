"""
SurrealDB Vector implementation of KnowledgeStore.

Requires: surrealdb
Install: pip install surrealdb
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class SurrealDBVectorKnowledgeStore(KnowledgeStore):
    """
    SurrealDB vector store for knowledge/RAG.
    
    Uses SurrealDB's vector capabilities.
    
    Example:
        store = SurrealDBVectorKnowledgeStore(
            url="ws://localhost:8000/rpc",
            namespace="praisonai",
            database="vectors"
        )
    """
    
    def __init__(
        self,
        url: str = "ws://localhost:8000/rpc",
        namespace: str = "praisonai",
        database: str = "vectors",
        username: str = "root",
        password: str = "root",
        embedding_dim: int = 1536,
    ):
        """
        Initialize SurrealDB Vector store.
        
        Args:
            url: SurrealDB WebSocket URL
            namespace: SurrealDB namespace
            database: SurrealDB database
            username: Authentication username
            password: Authentication password
            embedding_dim: Embedding dimension
        """
        self.url = url
        self.namespace = namespace
        self.database = database
        self.username = username
        self.password = password
        self.embedding_dim = embedding_dim
        
        self._client = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize SurrealDB client lazily."""
        if self._initialized:
            return
        
        try:
            from surrealdb import Surreal
        except ImportError:
            raise ImportError(
                "surrealdb is required for SurrealDB Vector support. "
                "Install with: pip install surrealdb"
            )
        
        import asyncio
        
        async def connect():
            client = Surreal(self.url)
            await client.connect()
            await client.signin({"user": self.username, "pass": self.password})
            await client.use(self.namespace, self.database)
            return client
        
        loop = asyncio.get_event_loop()
        self._client = loop.run_until_complete(connect())
        self._initialized = True
    
    def _run_async(self, coro):
        """Run async coroutine synchronously."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a collection (SurrealDB creates tables on insert)."""
        self._init_client()
        # SurrealDB creates tables automatically
        logger.info(f"Collection '{name}' will be created on first insert")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        self._init_client()
        try:
            self._run_async(self._client.query(f"REMOVE TABLE {name}"))
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        self._init_client()
        try:
            result = self._run_async(self._client.query(f"INFO FOR TABLE {name}"))
            return bool(result)
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        self._init_client()
        try:
            result = self._run_async(self._client.query("INFO FOR DB"))
            if result and len(result) > 0:
                tables = result[0].get("result", {}).get("tables", {})
                return list(tables.keys())
            return []
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        ids = []
        for doc in documents:
            record = {
                "content": doc.content,
                "embedding": doc.embedding,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            try:
                result = self._run_async(
                    self._client.create(f"{collection}:{doc.id}", record)
                )
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to insert document {doc.id}: {e}")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents."""
        self._init_client()
        
        ids = []
        for doc in documents:
            record = {
                "content": doc.content,
                "embedding": doc.embedding,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            try:
                self._run_async(
                    self._client.update(f"{collection}:{doc.id}", record)
                )
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to upsert document {doc.id}: {e}")
        
        return ids
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using vector search."""
        self._init_client()
        
        # SurrealDB vector search query
        embedding_str = str(query_embedding)
        query = f"""
            SELECT *, vector::similarity::cosine(embedding, {embedding_str}) AS score
            FROM {collection}
            ORDER BY score DESC
            LIMIT {limit}
        """
        
        try:
            result = self._run_async(self._client.query(query))
            
            documents = []
            if result and len(result) > 0:
                for row in result[0].get("result", []):
                    score = row.get("score", 0)
                    if score_threshold and score < score_threshold:
                        continue
                    
                    doc_id = str(row.get("id", "")).split(":")[-1]
                    documents.append(KnowledgeDocument(
                        id=doc_id,
                        content=row.get("content", ""),
                        embedding=row.get("embedding"),
                        metadata={**(row.get("metadata") or {}), "score": score},
                        content_hash=row.get("content_hash"),
                        created_at=row.get("created_at", 0)
                    ))
            
            return documents
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        documents = []
        for doc_id in ids:
            try:
                result = self._run_async(self._client.select(f"{collection}:{doc_id}"))
                if result:
                    row = result if isinstance(result, dict) else result[0]
                    documents.append(KnowledgeDocument(
                        id=doc_id,
                        content=row.get("content", ""),
                        embedding=row.get("embedding"),
                        metadata=row.get("metadata"),
                        content_hash=row.get("content_hash"),
                        created_at=row.get("created_at", 0)
                    ))
            except Exception as e:
                logger.warning(f"Failed to get document {doc_id}: {e}")
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        count = 0
        if ids:
            for doc_id in ids:
                try:
                    self._run_async(self._client.delete(f"{collection}:{doc_id}"))
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {doc_id}: {e}")
        else:
            try:
                self._run_async(self._client.query(f"DELETE FROM {collection}"))
                count = -1  # Unknown count
            except Exception as e:
                logger.error(f"Failed to delete all: {e}")
        
        return count
    
    def count(self, collection: str) -> int:
        """Count documents."""
        self._init_client()
        
        try:
            result = self._run_async(
                self._client.query(f"SELECT count() FROM {collection} GROUP ALL")
            )
            if result and len(result) > 0:
                return result[0].get("result", [{}])[0].get("count", 0)
            return 0
        except Exception as e:
            logger.error(f"Count failed: {e}")
            return 0
    
    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._run_async(self._client.close())
            self._client = None
            self._initialized = False
